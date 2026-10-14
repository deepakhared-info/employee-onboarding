import asyncio

from src.external.breaker import external_breaker


class HROperations:
    @external_breaker("hr_operations")
    async def register_employee(self, email: str, *, idempotency_key: str) -> bool:
        """Simulate registering the employee in the HR system."""
        await asyncio.sleep(1)
        return True


hr_operations = HROperations()
