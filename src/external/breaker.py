from src.core.config import settings
from src.core.resilience import circuit_breaker
from src.external.errors import TRANSIENT_ERRORS


def external_breaker(name: str):
    """Circuit breaker + call timeout with the project-wide external-service settings."""
    return circuit_breaker(
        name=name,
        failure_threshold=settings.CIRCUIT_FAILURE_THRESHOLD,
        recovery_timeout=settings.CIRCUIT_RECOVERY_TIMEOUT,
        expected_exceptions=TRANSIENT_ERRORS,
        timeout=settings.EXTERNAL_CALL_TIMEOUT,
    )
