import os
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _parse_int_list(raw: str) -> list[int]:
    """Парсит строку с числами через запятую."""
    if not raw.strip():
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_energy_package(env_key: str, name: str) -> dict[str, Any] | None:
    """Парсит пакет энергии из env переменной."""
    raw = os.getenv(env_key, "")
    if not raw:
        return None
    parts = raw.split(",")
    if len(parts) < 2:
        return None
    return {
        "name": name,
        "energy": int(parts[0]),
        "price_rub": int(parts[1]),
        "description": parts[2] if len(parts) > 2 else "",
    }


def _load_energy_packages() -> dict[str, dict[str, Any]]:
    """Загружает все пакеты энергии из env."""
    packages = {}
    
    pkg_70k = _parse_energy_package("ENERGY_PACKAGE_70K", "70k")
    if pkg_70k:
        packages["70k"] = pkg_70k
    
    pkg_140k = _parse_energy_package("ENERGY_PACKAGE_140K", "140k")
    if pkg_140k:
        packages["140k"] = pkg_140k
    
    # Дефолты если не заданы
    if not packages:
        packages = {
            "70k": {"name": "70k", "energy": 70_000, "price_rub": 100, "description": "Для кошелька с USDT"},
            "140k": {"name": "140k", "energy": 140_000, "price_rub": 200, "description": "Для пустого кошелька"},
        }
    
    return packages


@dataclass(frozen=True)
class Config:
    """Иммутабельная конфигурация бота."""
    
    # Telegram
    BOT_TOKEN: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    BOT_USERNAME: str = field(default_factory=lambda: os.getenv("BOT_USERNAME", ""))
    ADMIN_IDS: list[int] = field(default_factory=lambda: _parse_int_list(os.getenv("ADMIN_IDS", "")))
    
    # TRON
    TRON_PRIVATE_KEY: str = field(default_factory=lambda: os.getenv("TRON_PRIVATE_KEY", ""))
    TRON_WALLET_ADDRESS: str = field(default_factory=lambda: os.getenv("TRON_WALLET_ADDRESS", ""))
    TRONGRID_API_KEY: str = field(default_factory=lambda: os.getenv("TRONGRID_API_KEY", ""))
    TRON_NETWORK: str = field(default_factory=lambda: os.getenv("TRON_NETWORK", "mainnet"))
    
    # LOLZ
    LOLZ_API_TOKEN: str = field(default_factory=lambda: os.getenv("LOLZ_API_TOKEN", ""))
    LOLZ_MERCHANT_ID: int = field(default_factory=lambda: int(os.getenv("LOLZ_MERCHANT_ID", "125")))
    
    # Database
    DATABASE_URL: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///tron_energy.db"))
    
    # Energy
    ENERGY_PRICE_TRX: float = field(default_factory=lambda: float(os.getenv("ENERGY_PRICE_TRX", "0.000015")))
    MAX_ENERGY_PER_ORDER: int = field(default_factory=lambda: int(os.getenv("MAX_ENERGY_PER_ORDER", "1000000")))
    ENERGY_RETURN_TIME: int = field(default_factory=lambda: int(os.getenv("ENERGY_RETURN_TIME", "3600")))
    ENERGY_PER_USDT_TRANSFER: int = 28000
    
    # Commissions
    COMMISSION_WITH_USDT: int = field(default_factory=lambda: int(os.getenv("COMMISSION_WITH_USDT", "6770000")))
    COMMISSION_WITHOUT_USDT: int = field(default_factory=lambda: int(os.getenv("COMMISSION_WITHOUT_USDT", "13370000")))
    COMMISSION_DISCOUNTED: int = field(default_factory=lambda: int(os.getenv("COMMISSION_DISCOUNTED", "3000000")))
    COMMISSION_DISCOUNTED_HIGH: int = field(default_factory=lambda: int(os.getenv("COMMISSION_DISCOUNTED_HIGH", "6000000")))
    
    # Limits
    MAX_PENDING_ORDERS: int = field(default_factory=lambda: int(os.getenv("MAX_PENDING_ORDERS", "3")))
    RATE_LIMIT_REQUESTS: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_REQUESTS", "30")))
    RATE_LIMIT_WINDOW: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_WINDOW", "60")))
    
    # Support
    SUPPORT_USERNAME: str = field(default_factory=lambda: os.getenv("SUPPORT_USERNAME", "@support"))


# Singleton
config = Config()

# Пакеты энергии (загружаются отдельно т.к. сложная структура)
ENERGY_PACKAGES = _load_energy_packages()
