from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLOUD_", env_file=".env", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://ioniq5:ioniq5@localhost:5432/ioniq5"
    # Signs user session tokens. Rotating it logs everyone out.
    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_minutes: int = 60 * 12
    # Mixed into agent API key hashes so a leaked database alone doesn't let an
    # attacker recompute them.
    api_key_pepper: str = "dev-only-change-me"
    enrollment_code_ttl_minutes: int = 60
    # Rejects readings dated implausibly far ahead, which are almost always a
    # clock-skewed agent rather than real data.
    max_future_skew_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
