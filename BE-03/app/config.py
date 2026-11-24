"""Central configuration. Everything comes from environment variables so the
same image runs locally, in docker-compose and in production."""
import os


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Used to HMAC API keys before storing them and to sign login tokens.
    KEY_PEPPER: str = os.getenv("KEY_PEPPER", "dev-pepper-change-me")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-jwt-secret-change-me")
    JWT_TTL_SECONDS: int = int(os.getenv("JWT_TTL_SECONDS", "43200"))

    # Stripe (test mode keys start with sk_test_ / price_ / whsec_)
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRO_PRICE_ID: str = os.getenv("STRIPE_PRO_PRICE_ID", "")
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "http://localhost:8000")

    CELERY_ALWAYS_EAGER: bool = os.getenv("CELERY_ALWAYS_EAGER", "0") == "1"
    USAGE_FLUSH_SECONDS: int = int(os.getenv("USAGE_FLUSH_SECONDS", "15"))


settings = Settings()
