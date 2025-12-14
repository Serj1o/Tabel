from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    BOT_TOKEN: str
    BASE_URL: str
    WEBHOOK_SECRET: str
    DATABASE_URL: str
    TZ: str = "Europe/Moscow"

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 465
    SMTP_USER: str | None = None
    SMTP_PASS: str | None = None
    REPORT_EMAILS: str | None = None  # comma-separated

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
