import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class ProvisioningService(str, enum.Enum):
    HR_OPERATIONS = "hr_operations"
    IT_SERVICES = "it_services"
    ACCESS_PROVISION = "access_provision"


class ProvisioningStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"  # attempts exhausted or permanent error; kept as a dead letter


class ProvisioningTask(Base):
    """
    Outbox row: one external-service call to make for an employee. Written in the same
    transaction as the employee, then executed by a worker (at-least-once delivery).
    """

    __table_args__ = (
        UniqueConstraint("employee_id", "service"),
        Index("ix_provisioningtask_status_next_run_at", "status", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employee.id", ondelete="CASCADE"), index=True)
    service: Mapped[ProvisioningService] = mapped_column(
        Enum(ProvisioningService, native_enum=False, length=30)
    )
    status: Mapped[ProvisioningStatus] = mapped_column(
        Enum(ProvisioningStatus, native_enum=False, length=20), default=ProvisioningStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(default=0)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
