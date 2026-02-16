import os
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable, TypeVar
from dataclasses import dataclass, field
from enum import Enum

from py_clob_client.client import ClobClient as OfficialClobClient
from py_clob_client.clob_types import ApiCreds, OrderType as OfficialOrderType, OrderArgs
from py_builder_signing_sdk.config import BuilderConfig as OfficialBuilderConfig
from py_builder_signing_sdk.sdk_types import BuilderApiKeyCreds

from .config import Config, BuilderConfig
from .client import RelayerClient
from .crypto import KeyManager, CryptoError, InvalidPasswordError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

T = TypeVar("T")


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    GTC = "GTC"
    GTD = "GTD"
    FOK = "FOK"


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    status: Optional[str] = None
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_response(cls, response: Dict[str, Any]) -> "OrderResult":
        success = response.get("success", False)
        error_msg = response.get("errorMsg", "")
        return cls(
            success=success,
            order_id=response.get("orderId"),
            status=response.get("status"),
            message=error_msg if not success else "Order placed successfully",
            data=response
        )


class TradingBotError(Exception):
    pass


class NotInitializedError(TradingBotError):
    pass


class TradingBot:
    def __init__(
        self,
        config_path: Optional[str] = None,
        config: Optional[Config] = None,
        safe_address: Optional[str] = None,
        builder_creds: Optional[BuilderConfig] = None,
        private_key: Optional[str] = None,
        encrypted_key_path: Optional[str] = None,
        password: Optional[str] = None,
        api_creds_path: Optional[str] = None,
        log_level: int = logging.INFO
    ):
        logger.setLevel(log_level)
        if config_path:
            self.config = Config.load(config_path)
        elif config:
            self.config = config
        else:
            self.config = Config()
        if safe_address:
            self.config.safe_address = safe_address
        if builder_creds:
            self.config.builder = builder_creds
            self.config.use_gasless = True

        self._private_key: Optional[str] = None
        self.clob_client: Optional[OfficialClobClient] = None
        self.relayer_client: Optional[RelayerClient] = None

        if private_key:
            self._private_key = private_key
        elif encrypted_key_path and password:
            self._private_key = self._load_encrypted_key(encrypted_key_path, password)

        self._init_clients()
        logger.info(f"TradingBot initialized (gasless: {self.config.use_gasless})")

    def _load_encrypted_key(self, filepath: str, password: str) -> str:
        try:
            manager = KeyManager()
            private_key = manager.load_and_decrypt(password, filepath)
            logger.info(f"Loaded encrypted key from {filepath}")
            return private_key
        except FileNotFoundError:
            raise TradingBotError(f"Encrypted key file not found: {filepath}")
        except InvalidPasswordError:
            raise TradingBotError("Invalid password for encrypted key")
        except CryptoError as e:
            raise TradingBotError(f"Failed to load encrypted key: {e}")

    def _init_clients(self) -> None:
        # Build official BuilderConfig if we have builder credentials
        official_builder_config = None
        if self.config.use_gasless and self.config.builder.is_configured():
            official_builder_config = OfficialBuilderConfig(
                local_builder_creds=BuilderApiKeyCreds(
                    key=self.config.builder.api_key,
                    secret=self.config.builder.api_secret,
                    passphrase=self.config.builder.api_passphrase,
                )
            )
            logger.info("Builder config created for gasless trading")

        # Initialize official ClobClient (Level 1 - key only, no creds yet)
        self.clob_client = OfficialClobClient(
            host=self.config.clob.host,
            chain_id=self.config.clob.chain_id,
            key=self._private_key,
            signature_type=self.config.clob.signature_type,
            funder=self.config.safe_address,
            builder_config=official_builder_config,
        )

        # Derive L2 API credentials using official client
        if self._private_key:
            try:
                logger.info("Deriving L2 API credentials via official client...")
                creds = self.clob_client.create_or_derive_api_creds()
                self.clob_client.set_api_creds(creds)
                logger.info("L2 API credentials derived successfully")
            except Exception as e:
                logger.warning(f"Failed to derive API credentials: {e}")

        # Initialize relayer client for safe deployment
        if self.config.use_gasless:
            self.relayer_client = RelayerClient(
                host=self.config.relayer.host,
                chain_id=self.config.clob.chain_id,
                builder_creds=self.config.builder,
                tx_type=self.config.relayer.tx_type,
            )
            logger.info("Relayer client initialized (gasless enabled)")

    async def _run_in_thread(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        return await asyncio.to_thread(func, *args, **kwargs)

    def is_initialized(self) -> bool:
        return (
            self._private_key is not None and
            bool(self.config.safe_address) and
            self.clob_client is not None
        )

    def _require_key(self) -> str:
        if not self._private_key:
            raise NotInitializedError("Private key not initialized. Provide private_key or encrypted_key.")
        return self._private_key

    def _get_order_type(self, order_type: str) -> OfficialOrderType:
        mapping = {
            "GTC": OfficialOrderType.GTC,
            "GTD": OfficialOrderType.GTD,
            "FOK": OfficialOrderType.FOK,
        }
        return mapping.get(order_type.upper(), OfficialOrderType.GTC)

    def _create_and_post_order(self, token_id: str, price: float, size: float, side: str, order_type: str, fee_rate_bps: int) -> Dict[str, Any]:
        """Synchronous method that creates, signs, and posts an order using official client."""
        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=side.upper(),
            fee_rate_bps=fee_rate_bps,
        )
        signed_order = self.clob_client.create_order(order_args)
        return self.clob_client.post_order(signed_order, self._get_order_type(order_type))

    def _create_and_post_orders_batch(self, orders: List[Dict[str, Any]], order_type: str, fee_rate_bps: int = 0) -> Dict[str, Any]:
        """Synchronous method that creates, signs, and posts multiple orders in a batch using official client."""
        signed_orders = []
        for order_data in orders:
            order_args = OrderArgs(
                token_id=order_data["token_id"],
                price=order_data["price"],
                size=order_data["size"],
                side=order_data["side"].upper(),
                fee_rate_bps=fee_rate_bps,
            )
            signed_order = self.clob_client.create_order(order_args)
            signed_orders.append(signed_order)
        
        # Try to use batch endpoint if available, otherwise fall back to individual posts
        if hasattr(self.clob_client, 'post_orders'):
            return self.clob_client.post_orders(signed_orders, self._get_order_type(order_type))
        else:
            # Fallback: post orders individually (but still faster than async parallel)
            results = []
            for signed_order in signed_orders:
                try:
                    result = self.clob_client.post_order(signed_order, self._get_order_type(order_type))
                    results.append(result)
                except Exception as e:
                    results.append({"success": False, "errorMsg": str(e)})
            return {"results": results}

    async def place_order(self, token_id: str, price: float, size: float, side: str, order_type: str = "GTC", fee_rate_bps: int = 0) -> OrderResult:
        self._require_key()
        try:
            response = await self._run_in_thread(
                self._create_and_post_order,
                token_id, price, size, side, order_type, fee_rate_bps,
            )
            logger.info(f"Order placed: {side} {size}@{price} (token: {token_id[:16]}...)")
            return OrderResult.from_response(response)
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return OrderResult(success=False, message=str(e))

    async def place_orders(self, orders: List[Dict[str, Any]], order_type: str = "GTC") -> List[OrderResult]:
        results = []
        for order_data in orders:
            result = await self.place_order(
                token_id=order_data["token_id"], price=order_data["price"],
                size=order_data["size"], side=order_data["side"], order_type=order_type,
            )
            results.append(result)
            await asyncio.sleep(0.1)
        return results

    async def place_orders_batch(self, orders: List[Dict[str, Any]], order_type: str = "GTC", fee_rate_bps: int = 0) -> List[OrderResult]:
        """Place multiple orders in a single batch request."""
        self._require_key()
        try:
            response = await self._run_in_thread(
                self._create_and_post_orders_batch,
                orders, order_type, fee_rate_bps,
            )
            # Batch response may contain multiple order results
            # Handle both single result dict and array of results
            if isinstance(response, list):
                return [OrderResult.from_response(r) for r in response]
            elif isinstance(response, dict):
                # Check if response contains an array of results
                if "results" in response:
                    return [OrderResult.from_response(r) for r in response["results"]]
                elif "data" in response and isinstance(response["data"], list):
                    return [OrderResult.from_response(r) for r in response["data"]]
                else:
                    # Single result in batch response
                    return [OrderResult.from_response(response)]
            else:
                logger.warning(f"Unexpected batch response format: {response}")
                return [OrderResult(success=False, message="Unexpected response format")]
        except Exception as e:
            logger.error(f"Failed to place batch orders: {e}")
            return [OrderResult(success=False, message=str(e)) for _ in orders]

    async def cancel_order(self, order_id: str) -> OrderResult:
        try:
            response = await self._run_in_thread(self.clob_client.cancel, order_id)
            logger.info(f"Order cancelled: {order_id}")
            return OrderResult(success=True, order_id=order_id, message="Order cancelled", data=response)
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return OrderResult(success=False, order_id=order_id, message=str(e))

    async def cancel_all_orders(self) -> OrderResult:
        try:
            response = await self._run_in_thread(self.clob_client.cancel_all)
            logger.info("All orders cancelled")
            return OrderResult(success=True, message="All orders cancelled", data=response)
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")
            return OrderResult(success=False, message=str(e))

    async def cancel_market_orders(self, market: Optional[str] = None, asset_id: Optional[str] = None) -> OrderResult:
        try:
            response = await self._run_in_thread(
                self.clob_client.cancel_market_orders,
                market or "",
                asset_id or "",
            )
            logger.info(f"Market orders cancelled (market: {market or 'all'})")
            return OrderResult(success=True, message=f"Orders cancelled for market {market or 'all'}", data=response)
        except Exception as e:
            logger.error(f"Failed to cancel market orders: {e}")
            return OrderResult(success=False, message=str(e))

    async def get_open_orders(self) -> List[Dict[str, Any]]:
        try:
            orders = await self._run_in_thread(self.clob_client.get_orders)
            return orders if isinstance(orders, list) else []
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._run_in_thread(self.clob_client.get_order, order_id)
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None

    async def get_trades(self, token_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            trades = await self._run_in_thread(self.clob_client.get_trades)
            return trades if isinstance(trades, list) else []
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    async def get_order_book(self, token_id: str) -> Dict[str, Any]:
        try:
            return await self._run_in_thread(self.clob_client.get_order_book, token_id)
        except Exception as e:
            logger.error(f"Failed to get order book: {e}")
            return {}

    async def get_market_price(self, token_id: str) -> Dict[str, Any]:
        try:
            return await self._run_in_thread(self.clob_client.get_last_trade_price, token_id)
        except Exception as e:
            logger.error(f"Failed to get market price: {e}")
            return {}

    async def deploy_safe_if_needed(self) -> bool:
        if not self.config.use_gasless or not self.relayer_client:
            return False
        try:
            response = await self._run_in_thread(self.relayer_client.deploy_safe, self.config.safe_address)
            logger.info(f"Safe deployment initiated: {response}")
            return True
        except Exception as e:
            logger.warning(f"Safe deployment failed (may already be deployed): {e}")
            return False

    def create_order_dict(self, token_id: str, price: float, size: float, side: str) -> Dict[str, Any]:
        return {"token_id": token_id, "price": price, "size": size, "side": side.upper()}


def create_bot(config_path: str = "config.yaml", private_key: Optional[str] = None, encrypted_key_path: Optional[str] = None, password: Optional[str] = None, **kwargs) -> TradingBot:
    return TradingBot(config_path=config_path, private_key=private_key, encrypted_key_path=encrypted_key_path, password=password, **kwargs)
