from .start import router as start_router
from .buy_energy import router as buy_energy_router
from .check_energy import router as check_energy_router
from .history import router as history_router
from .admin import router as admin_router
from .profile import router as profile_router
from .balance import router as balance_router

__all__ = [
    "start_router",
    "buy_energy_router",
    "check_energy_router",
    "history_router",
    "admin_router",
    "profile_router",
    "balance_router",
]
