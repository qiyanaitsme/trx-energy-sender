from config import config

TARGET_WIDTH = 45


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def pad_message(text: str) -> str:
    padding_line = "ㅤ" * TARGET_WIDTH
    return f"{text}\n{padding_line}"


def format_box(title: str, content: str) -> str:
    padding_line = "ㅤ" * TARGET_WIDTH
    return f"{title}\n\n{content}\n{padding_line}"


def mask_address(address: str) -> str:
    """Маскирует TRON адрес для безопасного логирования."""
    if not address or len(address) < 10:
        return "N/A"
    return f"{address[:6]}...{address[-4:]}"


def mask_tx_hash(tx_hash: str) -> str:
    """Маскирует хеш транзакции для отображения."""
    if not tx_hash or len(tx_hash) < 20:
        return tx_hash or "N/A"
    return f"{tx_hash[:16]}..."
