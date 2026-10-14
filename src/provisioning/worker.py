"""
In-process runner for provisioning tasks. Replaceable by Celery: keep
`ProvisioningProcessor.process` and swap this class for a dispatcher that enqueues
`process(task_id)` (see processor.py) and set PROVISIONING_WORKER_ENABLED=False.
"""

import asyncio
import contextlib
import logging
from typing import Sequence

from src.core.config import settings
from src.db.session import SessionLocal
from src.provisioning.db import ProvisioningTaskDBManager, provisioning_task_manager
from src.provisioning.processor import ProvisioningProcessor, provisioning_processor

logger = logging.getLogger(__name__)


class ProvisioningWorker:
    """Polls the task table; `dispatch` just wakes it so new tasks start without waiting."""

    def __init__(
        self,
        processor: ProvisioningProcessor = provisioning_processor,
        tasks: ProvisioningTaskDBManager = provisioning_task_manager,
    ):
        self.processor = processor
        self.tasks = tasks
        self._wake = asyncio.Event()
        self._runner: asyncio.Task | None = None

    def dispatch(self, task_ids: Sequence[int]) -> None:
        self._wake.set()

    async def start(self) -> None:
        if self._runner is None:
            self._runner = asyncio.create_task(self._run(), name="provisioning-worker")

    async def stop(self) -> None:
        if self._runner is not None:
            self._runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner
            self._runner = None

    async def _run(self) -> None:
        while True:
            self._wake.clear()  # before polling, so a dispatch during the tick isn't lost
            try:
                handled = await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Provisioning worker tick failed")
                handled = 0
            if handled >= settings.PROVISIONING_BATCH_SIZE:
                continue  # backlog: go again immediately
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), settings.PROVISIONING_POLL_INTERVAL)

    async def _tick(self) -> int:
        async with SessionLocal() as db:
            # Tasks for services behind an open circuit stay queued, untouched.
            ids = await self.tasks.list_due_ids(
                db,
                limit=settings.PROVISIONING_BATCH_SIZE,
                exclude=self.processor.open_services(),
            )
        semaphore = asyncio.Semaphore(settings.PROVISIONING_CONCURRENCY)

        async def run(task_id: int) -> None:
            async with semaphore:
                await self.processor.process(task_id)

        results = await asyncio.gather(*(run(i) for i in ids), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                logger.error("Provisioning task crashed", exc_info=result)
        return len(ids)


provisioning_worker = ProvisioningWorker()
