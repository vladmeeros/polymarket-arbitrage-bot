from typing import Tuple

from .config import Config, get_env
from .bot import TradingBot
from .crypto import verify_private_key


def validate_address(address: str) -> bool:
    if not address:
        return False
    if not address.startswith("0x"):
        return False
    if len(address) != 42:
        return False
    try:
        int(address, 16)
        return True
    except ValueError:
        return False


def validate_private_key(key: str) -> Tuple[bool, str]:
    if not key:
        return False, "Private key cannot be empty"
    is_valid, result = verify_private_key(key)
    if is_valid:
        return True, result
    if "64 hex characters" in result:
        return False, "Private key must be 64 hex characters (32 bytes)"
    if "invalid characters" in result.lower():
        return False, "Private key contains invalid characters"
    return False, result


def format_price(price: float, decimals: int = 2) -> str:
    percentage = price * 100
    return f"{price:.{decimals}f} ({percentage:.0f}%)"


def format_usdc(amount: float, decimals: int = 2) -> str:
    return f"${amount:.{decimals}f} USDC"


def create_bot_from_env() -> TradingBot:
    private_key = get_env("PRIVATE_KEY")
    if not private_key:
        raise ValueError(
            "POLY_PRIVATE_KEY environment variable is required. "
            "Set it with: export POLY_PRIVATE_KEY=your_key"
        )
    safe_address = get_env("PROXY_WALLET") or get_env("SAFE_ADDRESS")
    if not safe_address:
        raise ValueError(
            "POLY_PROXY_WALLET or POLY_SAFE_ADDRESS environment variable is required."
        )
    config = Config.from_env()
    return TradingBot(config=config, private_key=private_key)


def truncate_address(address: str, chars: int = 6) -> str:
    if not address or len(address) < chars * 2 + 2:
        return address
    return f"{address[:chars + 2]}...{address[-chars:]}"


def truncate_token_id(token_id: str, chars: int = 8) -> str:
    if not token_id or len(token_id) <= chars:
        return token_id
    return f"{token_id[:chars]}..."


__all__ = [
    "validate_address",
    "validate_private_key",
    "format_price",
    "format_usdc",
    "get_env",
    "create_bot_from_env",
    "truncate_address",
    "truncate_token_id",
]
