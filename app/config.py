from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ledger"

    default_page_size: int = 10
    max_page_size: int = 100

    sql_echo: bool = False


settings = Settings()
