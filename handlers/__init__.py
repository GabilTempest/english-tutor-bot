from .common import router as common_router
from .lessons import router as lessons_router
from .homework import router as homework_router
from .settings import router as settings_router
from .balance import router as balance_router

routers = [
    common_router,
    lessons_router,
    homework_router,
    settings_router,
    balance_router
]
