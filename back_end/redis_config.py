"""Redis URL builder — reads from pydantic Settings (config.settings).

Settings loads `.env` itself, so REDIS_* values set there are honored even
though pydantic-settings never exports them into os.environ.
"""

from config import settings


def get_redis_url(db: int = 0) -> str:
    host = settings.REDIS_HOST
    port = settings.REDIS_PORT
    access_key = settings.REDIS_ACCESS_KEY
    if access_key:
        return f"rediss://:{access_key}@{host}:{port}/{db}?ssl_cert_reqs=none"
    return f"redis://{host}:{port}/{db}"


def get_masked_redis_url(db: int = 0) -> str:
    host = settings.REDIS_HOST
    port = settings.REDIS_PORT
    access_key = settings.REDIS_ACCESS_KEY
    if access_key:
        return f"rediss://:<MASKED>@{host}:{port}/{db}?ssl_cert_reqs=none"
    return f"redis://{host}:{port}/{db}"
