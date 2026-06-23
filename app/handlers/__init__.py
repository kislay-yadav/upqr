"""Register all routers."""
from app.handlers.common   import router as common_router
from app.handlers.generate import router as generate_router
from app.handlers.payees   import router as payees_router
from app.handlers.settings import router as settings_router
from app.handlers.admin    import router as admin_router
from app.handlers.owner    import router as owner_router

ALL_ROUTERS = [
    common_router,
    generate_router,
    payees_router,
    settings_router,
    admin_router,
    owner_router,
]
