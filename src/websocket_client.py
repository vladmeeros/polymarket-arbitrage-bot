import json
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable, Set, Union, Awaitable, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)

WSS_MARKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
WSS_USER_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"


def _load_websockets():
    try:
        from websockets.asyncio.client import connect as ws_connect
        from websockets.exceptions import ConnectionClosed
        return ws_connect, ConnectionClosed
    except ImportError:
        try:
            import websockets
            return websockets.connect, websockets.exceptions.ConnectionClosed
        except ImportError:
            return None, Exception


@dataclass
class OrderbookLevel:
    price: float
    size: float


@dataclass
class OrderbookSnapshot:
    asset_id: str
    market: str
    timestamp: int
    bids: List[OrderbookLevel] = field(default_factory=list)
    asks: List[OrderbookLevel] = field(default_factory=list)
    hash: str = ""

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 1.0

    @property
    def mid_price(self) -> float:
        if self.best_bid > 0 and self.best_ask < 1:
            return (self.best_bid + self.best_ask) / 2
        elif self.best_bid > 0:
            return self.best_bid
        elif self.best_ask < 1:
            return self.best_ask
        return 0.5

    @classmethod
    def from_message(cls, msg: Dict[str, Any]) -> "OrderbookSnapshot":
        bids = [
            OrderbookLevel(price=float(b["price"]), size=float(b["size"]))
            for b in msg.get("bids", [])
        ]
        asks = [
            OrderbookLevel(price=float(a["price"]), size=float(a["size"]))
            for a in msg.get("asks", [])
        ]
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)
        return cls(
            asset_id=msg.get("asset_id", ""),
            market=msg.get("market", ""),
            timestamp=int(msg.get("timestamp", 0)),
            bids=bids,
            asks=asks,
            hash=msg.get("hash", ""),
        )


@dataclass
class PriceChange:
    asset_id: str
    price: float
    size: float
    side: str
    best_bid: float
    best_ask: float
    hash: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PriceChange":
        return cls(
            asset_id=data.get("asset_id", ""),
            price=float(data.get("price", 0)),
            size=float(data.get("size", 0)),
            side=data.get("side", ""),
            best_bid=float(data.get("best_bid", 0)),
            best_ask=float(data.get("best_ask", 1)),
            hash=data.get("hash", ""),
        )


@dataclass
class LastTradePrice:
    asset_id: str
    market: str
    price: float
    size: float
    side: str
    timestamp: int
    fee_rate_bps: int = 0

    @classmethod
    def from_message(cls, msg: Dict[str, Any]) -> "LastTradePrice":
        return cls(
            asset_id=msg.get("asset_id", ""),
            market=msg.get("market", ""),
            price=float(msg.get("price", 0)),
            size=float(msg.get("size", 0)),
            side=msg.get("side", ""),
            timestamp=int(msg.get("timestamp", 0)),
            fee_rate_bps=int(msg.get("fee_rate_bps", 0)),
        )


BookCallback = Callable[[OrderbookSnapshot], Union[None, Awaitable[None]]]
PriceChangeCallback = Callable[[str, List[PriceChange]], Union[None, Awaitable[None]]]
TradeCallback = Callable[[LastTradePrice], Union[None, Awaitable[None]]]
ErrorCallback = Callable[[Exception], None]


class MarketWebSocket:
    def __init__(self, url: str = WSS_MARKET_URL, reconnect_interval: float = 5.0, ping_interval: float = 20.0, ping_timeout: float = 10.0):
        self.url = url
        self.reconnect_interval = reconnect_interval
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self._ws_connect, self._connection_closed = _load_websockets()
        self._ws: Optional["WebSocketClientProtocol"] = None
        self._running = False
        self._subscribed_assets: Set[str] = set()
        self._orderbooks: Dict[str, OrderbookSnapshot] = {}
        self._on_book: Optional[BookCallback] = None
        self._on_price_change: Optional[PriceChangeCallback] = None
        self._on_trade: Optional[TradeCallback] = None
        self._on_error: Optional[ErrorCallback] = None
        self._on_connect: Optional[Callable[[], None]] = None
        self._on_disconnect: Optional[Callable[[], None]] = None

    @property
    def is_connected(self) -> bool:
        if self._ws is None:
            return False
        try:
            from websockets.protocol import State
            return self._ws.state == State.OPEN
        except (ImportError, AttributeError):
            try:
                return self._ws.open
            except AttributeError:
                return False

    @property
    def orderbooks(self) -> Dict[str, OrderbookSnapshot]:
        return self._orderbooks

    def get_orderbook(self, asset_id: str) -> Optional[OrderbookSnapshot]:
        return self._orderbooks.get(asset_id)

    def get_mid_price(self, asset_id: str) -> float:
        ob = self._orderbooks.get(asset_id)
        return ob.mid_price if ob else 0.0

    def on_book(self, callback: BookCallback) -> BookCallback:
        self._on_book = callback
        return callback

    def on_price_change(self, callback: PriceChangeCallback) -> PriceChangeCallback:
        self._on_price_change = callback
        return callback

    def on_trade(self, callback: TradeCallback) -> TradeCallback:
        self._on_trade = callback
        return callback

    def on_error(self, callback: ErrorCallback) -> ErrorCallback:
        self._on_error = callback
        return callback

    def on_connect(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._on_connect = callback
        return callback

    def on_disconnect(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._on_disconnect = callback
        return callback

    async def connect(self) -> bool:
        try:
            if self._ws_connect is None:
                raise RuntimeError("websockets is not installed")
            self._ws = await self._ws_connect(
                self.url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
            )
            logger.info(f"WebSocket connected to {self.url}")
            if self._on_connect:
                self._on_connect()
            return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            if self._on_error:
                self._on_error(e)
            return False

    async def disconnect(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("WebSocket disconnected")
            if self._on_disconnect:
                self._on_disconnect()

    async def subscribe(self, asset_ids: List[str], replace: bool = False) -> bool:
        if not asset_ids:
            return False

        old_assets = set(self._subscribed_assets) if replace else set()

        if replace:
            self._subscribed_assets.clear()
            self._orderbooks.clear()
        self._subscribed_assets.update(asset_ids)
        logger.info(f"subscribe() called with {len(asset_ids)} assets, is_connected={self.is_connected}")
        if not self.is_connected:
            logger.info("Not connected yet, will subscribe after connect")
            return True

        try:
            # If already connected, use mid-connection operation format
            # First unsubscribe old assets if replacing
            if old_assets:
                unsub_msg = json.dumps({"assets_ids": list(old_assets), "operation": "unsubscribe"})
                logger.info(f"Unsubscribing old assets: {unsub_msg[:200]}")
                await self._ws.send(unsub_msg)

            # Subscribe to new assets using mid-connection format
            sub_msg = json.dumps({"assets_ids": asset_ids, "operation": "subscribe"})
            logger.info(f"Subscribing new assets: {sub_msg[:200]}")
            await self._ws.send(sub_msg)
            logger.info(f"Subscribed to {len(asset_ids)} assets successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            if self._on_error:
                self._on_error(e)
            return False

    async def subscribe_more(self, asset_ids: List[str]) -> bool:
        if not asset_ids:
            return False
        self._subscribed_assets.update(asset_ids)
        if not self.is_connected:
            return True
        subscribe_msg = {"assets_ids": asset_ids, "operation": "subscribe"}
        try:
            await self._ws.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to {len(asset_ids)} additional assets")
            return True
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            return False

    async def unsubscribe(self, asset_ids: List[str]) -> bool:
        if not self.is_connected or not asset_ids:
            return False
        self._subscribed_assets.difference_update(asset_ids)
        unsubscribe_msg = {"assets_ids": asset_ids, "operation": "unsubscribe"}
        try:
            await self._ws.send(json.dumps(unsubscribe_msg))
            logger.info(f"Unsubscribed from {len(asset_ids)} assets")
            return True
        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")
            return False

    async def _handle_message(self, data: Dict[str, Any]) -> None:
        event_type = data.get("event_type", "")
        logger.debug(f"Received event: {event_type}")
        if event_type == "book":
            snapshot = OrderbookSnapshot.from_message(data)
            self._orderbooks[snapshot.asset_id] = snapshot
            await self._run_callback(self._on_book, snapshot, label="book")
        elif event_type == "price_change":
            market = data.get("market", "")
            changes = [PriceChange.from_dict(pc) for pc in data.get("price_changes", [])]
            await self._run_callback(self._on_price_change, market, changes, label="price_change")
        elif event_type == "last_trade_price":
            trade = LastTradePrice.from_message(data)
            await self._run_callback(self._on_trade, trade, label="trade")

    async def _run_callback(self, callback: Optional[Callable[..., Any]], *args: Any, label: str) -> None:
        if not callback:
            return
        try:
            result = callback(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.error(f"Error in {label} callback: {e}")

    async def _run_loop(self) -> None:
        msg_count = 0
        while self._running and self.is_connected:
            try:
                message = await asyncio.wait_for(self._ws.recv(), timeout=self.ping_interval + 5)
                msg_count += 1
                if msg_count <= 5 or msg_count % 1000 == 0:
                    logger.info(f"WS message #{msg_count}: {message[:200] if len(message) > 200 else message}")
                data = json.loads(message)
                if isinstance(data, list):
                    for item in data:
                        await self._handle_message(item)
                else:
                    await self._handle_message(data)
            except asyncio.TimeoutError:
                logger.warning("WebSocket receive timeout")
            except self._connection_closed as e:
                logger.warning(f"WebSocket connection closed: {e}")
                break
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message: {e}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                if self._on_error:
                    self._on_error(e)

    async def run(self, auto_reconnect: bool = True) -> None:
        self._running = True
        while self._running:
            if not await self.connect():
                if auto_reconnect:
                    logger.info(f"Reconnecting in {self.reconnect_interval}s...")
                    await asyncio.sleep(self.reconnect_interval)
                    continue
                else:
                    break
            if self._subscribed_assets:
                logger.info(f"Sending initial subscription for {len(self._subscribed_assets)} assets after connect")
                # Initial connection uses "type": "MARKET" format
                init_msg = json.dumps({"assets_ids": list(self._subscribed_assets), "type": "MARKET"})
                await self._ws.send(init_msg)
            await self._run_loop()
            if self._on_disconnect:
                self._on_disconnect()
            if not self._running:
                break
            if auto_reconnect:
                logger.info(f"Reconnecting in {self.reconnect_interval}s...")
                await asyncio.sleep(self.reconnect_interval)
            else:
                break

    async def run_until_cancelled(self) -> None:
        try:
            await self.run(auto_reconnect=True)
        except asyncio.CancelledError:
            await self.disconnect()

    def stop(self) -> None:
        self._running = False


class OrderbookManager:
    def __init__(self):
        self._ws = MarketWebSocket()
        self._price_callback: Optional[Callable[[str, float, float, float], None]] = None
        self._connected = False

        @self._ws.on_book
        async def on_book(snapshot: OrderbookSnapshot):
            if self._price_callback:
                try:
                    result = self._price_callback(snapshot.asset_id, snapshot.mid_price, snapshot.best_bid, snapshot.best_ask)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Error in price callback: {e}")

        @self._ws.on_connect
        def on_connect():
            self._connected = True

        @self._ws.on_disconnect
        def on_disconnect():
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_price(self, asset_id: str) -> float:
        return self._ws.get_mid_price(asset_id)

    def get_orderbook(self, asset_id: str) -> Optional[OrderbookSnapshot]:
        return self._ws.get_orderbook(asset_id)

    def on_price_update(self, callback: Callable[[str, float, float, float], None]) -> Callable[[str, float, float, float], None]:
        self._price_callback = callback
        return callback

    async def start(self, asset_ids: List[str]) -> None:
        await self._ws.subscribe(asset_ids)
        await self._ws.run(auto_reconnect=True)

    async def subscribe(self, asset_ids: List[str]) -> bool:
        return await self._ws.subscribe_more(asset_ids)

    async def unsubscribe(self, asset_ids: List[str]) -> bool:
        return await self._ws.unsubscribe(asset_ids)

    def stop(self) -> None:
        self._ws.stop()

    async def close(self) -> None:
        await self._ws.disconnect()
