from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DEBUG: bool = True
    API_PREFIX: str = '/api'
    SQLALCHEMY_DATABASE_URI: str = ''


settings = Config()
