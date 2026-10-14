import asyncio

from src.external.breaker import external_breaker


class AccessProvision:
    @external_breaker("access_provision")
    async def grant_access(self, email: str, *, idempotency_key: str) -> bool:
        """Simulate granting system access to the employee."""
        await asyncio.sleep(1)
        return True


access_provision = AccessProvision()
