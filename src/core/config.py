from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DEBUG: bool = True
    API_PREFIX: str = '/api'
    SQLALCHEMY_DATABASE_URI: str = ''

    # Provisioning of newly onboarded employees (external services)
    CELERY_BROKER_URL: str = 'amqp://guest:guest@localhost:5672//'  # RabbitMQ
    PROVISIONING_MAX_ATTEMPTS: int = 5
    PROVISIONING_BACKOFF_BASE: float = 2.0
    PROVISIONING_BACKOFF_CAP: float = 300.0

    EXTERNAL_CALL_TIMEOUT: float = 10.0
    CIRCUIT_FAILURE_THRESHOLD: int = 5
    CIRCUIT_RECOVERY_TIMEOUT: float = 30.0


settings = Config()
