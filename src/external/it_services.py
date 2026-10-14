import asyncio

from src.external.breaker import external_breaker


class ITServices:
    @external_breaker("it_services")
    async def provision_laptop(self, email: str, *, idempotency_key: str) -> bool:
        """Simulate provisioning a laptop for the employee."""
        await asyncio.sleep(1)
        return True


it_services = ITServices()
