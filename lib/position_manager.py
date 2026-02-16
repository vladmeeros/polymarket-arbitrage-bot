import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Literal


ExitType = Literal["take_profit", "stop_loss", None]


@dataclass
class Position:
    id: str
    side: str
    token_id: str
    entry_price: float
    size: float
    entry_time: float
    order_id: Optional[str] = None
    take_profit_delta: float = 0.10
    stop_loss_delta: float = 0.05

    @property
    def take_profit_price(self) -> float:
        return self.entry_price + self.take_profit_delta

    @property
    def stop_loss_price(self) -> float:
        return self.entry_price - self.stop_loss_delta

    def get_pnl(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.size

    def get_pnl_percent(self, current_price: float) -> float:
        if self.entry_price > 0:
            return (current_price - self.entry_price) / self.entry_price * 100
        return 0.0

    def get_hold_time(self) -> float:
        return time.time() - self.entry_time

    def check_take_profit(self, current_price: float) -> bool:
        return current_price >= self.take_profit_price

    def check_stop_loss(self, current_price: float) -> bool:
        return current_price <= self.stop_loss_price


@dataclass
class PositionManager:
    take_profit: float = 0.10
    stop_loss: float = 0.05
    max_positions: int = 1
    _positions: Dict[str, Position] = field(default_factory=dict)
    _positions_by_side: Dict[str, str] = field(default_factory=dict)
    trades_opened: int = 0
    trades_closed: int = 0
    total_pnl: float = 0.0
    winning_trades: int = 0
    losing_trades: int = 0

    def __post_init__(self):
        self._positions = {}
        self._positions_by_side = {}

    @property
    def position_count(self) -> int:
        return len(self._positions)

    @property
    def can_open_position(self) -> bool:
        return self.position_count < self.max_positions

    @property
    def win_rate(self) -> float:
        total = self.winning_trades + self.losing_trades
        if total > 0:
            return self.winning_trades / total * 100
        return 0.0

    def open_position(self, side: str, token_id: str, entry_price: float, size: float, order_id: Optional[str] = None) -> Optional[Position]:
        if not self.can_open_position:
            return None
        if side in self._positions_by_side:
            return None
        pos_id = str(uuid.uuid4())[:8]
        position = Position(
            id=pos_id, side=side, token_id=token_id, entry_price=entry_price,
            size=size, entry_time=time.time(), order_id=order_id,
            take_profit_delta=self.take_profit, stop_loss_delta=self.stop_loss,
        )
        self._positions[pos_id] = position
        self._positions_by_side[side] = pos_id
        self.trades_opened += 1
        return position

    def close_position(self, position_id: str, realized_pnl: float = 0.0) -> Optional[Position]:
        if position_id not in self._positions:
            return None
        position = self._positions.pop(position_id)
        if position.side in self._positions_by_side:
            if self._positions_by_side[position.side] == position_id:
                del self._positions_by_side[position.side]
        self.trades_closed += 1
        self.total_pnl += realized_pnl
        if realized_pnl >= 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        return position

    def get_position(self, position_id: str) -> Optional[Position]:
        return self._positions.get(position_id)

    def get_position_by_side(self, side: str) -> Optional[Position]:
        pos_id = self._positions_by_side.get(side)
        if pos_id:
            return self._positions.get(pos_id)
        return None

    def get_all_positions(self) -> List[Position]:
        return list(self._positions.values())

    def has_position(self, side: str) -> bool:
        return side in self._positions_by_side

    def check_exit(self, position_id: str, current_price: float) -> tuple:
        position = self._positions.get(position_id)
        if not position:
            return (None, 0.0)
        pnl = position.get_pnl(current_price)
        if position.check_take_profit(current_price):
            return ("take_profit", pnl)
        if position.check_stop_loss(current_price):
            return ("stop_loss", pnl)
        return (None, pnl)

    def check_all_exits(self, prices: Dict[str, float]) -> List[tuple]:
        exits = []
        for position in self._positions.values():
            price = prices.get(position.side, 0)
            if price <= 0:
                continue
            exit_type, pnl = self.check_exit(position.id, price)
            if exit_type:
                exits.append((position, exit_type, pnl))
        return exits

    def get_unrealized_pnl(self, prices: Dict[str, float]) -> float:
        total = 0.0
        for position in self._positions.values():
            price = prices.get(position.side, 0)
            if price > 0:
                total += position.get_pnl(price)
        return total

    def get_total_pnl(self, prices: Dict[str, float]) -> float:
        return self.total_pnl + self.get_unrealized_pnl(prices)

    def get_stats(self) -> Dict:
        return {
            "trades_opened": self.trades_opened,
            "trades_closed": self.trades_closed,
            "open_positions": self.position_count,
            "total_pnl": self.total_pnl,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
        }

    def clear(self) -> None:
        self._positions.clear()
        self._positions_by_side.clear()

    def reset_stats(self) -> None:
        self.trades_opened = 0
        self.trades_closed = 0
        self.total_pnl = 0.0
        self.winning_trades = 0
        self.losing_trades = 0
