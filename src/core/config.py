from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DEBUG: bool = True
    API_PREFIX: str = '/api'
    SQLALCHEMY_DATABASE_URI: str = ''

    # Provisioning of newly onboarded employees (external services)
    PROVISIONING_WORKER_ENABLED: bool = True  # False when another runner (e.g. Celery) processes tasks
    PROVISIONING_POLL_INTERVAL: float = 5.0  # seconds between polls when idle
    PROVISIONING_BATCH_SIZE: int = 50
    PROVISIONING_CONCURRENCY: int = 10
    PROVISIONING_LEASE_SECONDS: int = 60  # a running task not finished in time is picked up again
    PROVISIONING_MAX_ATTEMPTS: int = 5
    PROVISIONING_BACKOFF_BASE: float = 2.0
    PROVISIONING_BACKOFF_CAP: float = 300.0

    EXTERNAL_CALL_TIMEOUT: float = 10.0
    CIRCUIT_FAILURE_THRESHOLD: int = 5
    CIRCUIT_RECOVERY_TIMEOUT: float = 30.0


settings = Config()
