"""Package routes — enregistre toutes les routeurs."""

from apps.api.routes.chat import router as chat_router
from apps.api.routes.sessions import router as sessions_router
from apps.api.routes.documents import router as documents_router
from apps.api.routes.profile import router as profile_router
from apps.api.routes.progress import router as progress_router
from apps.api.routes.models import router as models_router

__all__ = [
    "chat_router",
    "sessions_router",
    "documents_router",
    "profile_router",
    "progress_router",
    "models_router",
]
