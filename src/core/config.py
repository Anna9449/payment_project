import logging
import os
from logging import config as logging_config
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from core.logger import LOGGING

logging_config.dictConfig(LOGGING)
logger = logging.getLogger('')

ENV_FILE = Path(__file__).resolve().parents[2] / '.env'


class Postgres(BaseSettings):
    """Настройки Postgres (переменные POSTGRES_*)."""

    model_config = SettingsConfigDict(
        env_prefix='POSTGRES_',
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        extra='ignore'
    )

    host: str = 'localhost'
    port: int = 5432
    user: str
    password: str
    db: str

    @property
    def url(self) -> str:
        return (
            'postgresql+asyncpg://'
            f'{self.user}:{self.password}@'
            f'{self.host}:{self.port}/'
            f'{self.db}'
        )


class Settings(BaseSettings):
    """Настройки проекта."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        extra='ignore'
    )

    base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_name: str = 'Payment Service'
    debug: bool = False

    webhook_secret: str

    postgres: Postgres = Postgres()


settings = Settings()
