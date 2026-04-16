from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Chit Fund Platform"
    database_url: str = "sqlite:///./chit_fund.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
