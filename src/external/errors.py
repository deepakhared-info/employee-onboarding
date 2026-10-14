class ExternalServiceError(Exception):
    """Base class for failures reported by external services."""


class TransientServiceError(ExternalServiceError):
    """Temporary failure (network, 5xx, overload): worth retrying."""


class PermanentServiceError(ExternalServiceError):
    """The service rejected the request: retrying will not help."""


# Anything in here is retried and counts against the circuit breaker.
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    TransientServiceError,
    ConnectionError,
    TimeoutError,
)
