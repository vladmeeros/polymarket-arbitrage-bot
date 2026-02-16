"""
Polymarket Arbitrage Bot - Core Library

Provides:
- TradingBot: Main trading interface with order management
- Config: Configuration management (YAML + environment variables)
- OrderSigner: EIP-712 order signing for Polymarket
- ClobClient: CLOB API client for order book access
- RelayerClient: Gasless transaction support via Builder Program
- GammaClient: Market discovery API client
- KeyManager: Encrypted private key storage (PBKDF2 + Fernet)
- MarketWebSocket: Real-time WebSocket market data streaming
"""

from .bot import TradingBot, OrderResult, OrderSide, OrderType, create_bot
from .config import Config, BuilderConfig, ClobConfig, RelayerConfig
from .signer import OrderSigner, Order
from .client import ClobClient, RelayerClient, ApiCredentials
from .crypto import KeyManager, CryptoError, InvalidPasswordError
from .gamma_client import GammaClient
from .websocket_client import MarketWebSocket, OrderbookSnapshot, OrderbookLevel
from .utils import create_bot_from_env, validate_address, validate_private_key

__all__ = [
    "TradingBot",
    "OrderResult",
    "OrderSide",
    "OrderType",
    "create_bot",
    "Config",
    "BuilderConfig",
    "ClobConfig",
    "RelayerConfig",
    "OrderSigner",
    "Order",
    "ClobClient",
    "RelayerClient",
    "ApiCredentials",
    "KeyManager",
    "CryptoError",
    "InvalidPasswordError",
    "GammaClient",
    "MarketWebSocket",
    "OrderbookSnapshot",
    "OrderbookLevel",
    "create_bot_from_env",
    "validate_address",
    "validate_private_key",
]
