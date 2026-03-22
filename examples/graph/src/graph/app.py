import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from keyshield import ApiKeyService
from keyshield.api import create_depends_api_key
from keyshield.hasher.argon2 import Argon2ApiKeyHasher
from keyshield.repositories.in_memory import InMemoryApiKeyRepository

# Bootstrap sys.path so 'graph' is importable when loaded by aegra's spec loader
# (spec_from_file_location does not set __package__ or modify sys.path)
import sys as _sys
from pathlib import Path as _Path
_src = str(_Path(__file__).parent.parent.resolve())
if _src not in _sys.path:
    _sys.path.insert(0, _src)

from graph.ttl_sweeper import load_ttl_config, run_sweeper

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# API key authentication (keyshield)
# ---------------------------------------------------------------------------
pepper = os.getenv("SECRET_PEPPER")
hasher = Argon2ApiKeyHasher(pepper=pepper)
repo = InMemoryApiKeyRepository()
svc_api_keys = ApiKeyService(repo=repo, hasher=hasher)


def _server_url() -> str:
    """Resolve the local server URL from environment variables.

    Returns:
        The base URL string (e.g. ``http://localhost:8000``).
    """
    port = os.environ.get("PORT", "8000")
    return f"http://localhost:{port}"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Manage startup and shutdown for API keys and the TTL sweeper.

    On startup:
        - Loads API keys from ``.env``.
        - Starts the TTL sweeper background task if configured.

    On shutdown:
        - Cancels the sweeper task gracefully.

    Args:
        application: The FastAPI application instance.

    Yields:
        Control to the running application.
    """
    # --- Startup ---
    await svc_api_keys.load_dotenv()
    application.state.svc_api_keys = svc_api_keys

    sweeper_task = None
    ttl_config = load_ttl_config()

    if ttl_config and ttl_config.get("strategy") == "delete":
        sweeper_task = asyncio.create_task(
            run_sweeper(
                base_url=_server_url(),
                sweep_interval_minutes=int(
                    ttl_config.get("sweep_interval_minutes", 60)
                ),
                default_ttl_minutes=int(ttl_config.get("default_ttl", 20160)),
            )
        )
        logger.info("TTL sweeper background task started.")
    else:
        logger.info(
            "No TTL config found sweeper disabled. "
            "Add checkpointer.ttl to aegra.json to enable it."
        )

    yield  # --- App is running ---

    # --- Shutdown ---
    if sweeper_task and not sweeper_task.done():
        sweeper_task.cancel()
        try:
            await sweeper_task
        except asyncio.CancelledError:
            pass
        logger.info("TTL sweeper stopped.")


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------
async def get_svc_api_keys(request: Request) -> ApiKeyService:
    """Inject the API key service into route handlers.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The application-scoped ApiKeyService instance.
    """
    return request.app.state.svc_api_keys


security = create_depends_api_key(get_svc_api_keys)

# ---------------------------------------------------------------------------
# Standalone FastAPI app Aegra merges this with its own app at startup.
# DO NOT import or re-export aegra_api.main.app here.
# ---------------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)
