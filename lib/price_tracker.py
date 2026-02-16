import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Dict, Deque, List


@dataclass
class PricePoint:
    timestamp: float
    price: float
    side: str


@dataclass
class FlashCrashEvent:
    side: str
    old_price: float
    new_price: float
    drop: float
    timestamp: float

    @property
    def drop_percent(self) -> float:
        if self.old_price > 0:
            return (self.old_price - self.new_price) / self.old_price * 100
        return 0.0


@dataclass
class PriceTracker:
    lookback_seconds: int = 10
    drop_threshold: float = 0.30
    max_history: int = 100
    _history: Dict[str, Deque[PricePoint]] = field(default_factory=dict)

    def __post_init__(self):
        self._history = {
            "up": deque(maxlen=self.max_history),
            "down": deque(maxlen=self.max_history),
        }

    def record(self, side: str, price: float, timestamp: Optional[float] = None) -> None:
        if side not in self._history:
            return
        if price <= 0:
            return
        ts = timestamp if timestamp is not None else time.time()
        self._history[side].append(PricePoint(timestamp=ts, price=price, side=side))

    def record_prices(self, prices: Dict[str, float]) -> None:
        now = time.time()
        for side, price in prices.items():
            self.record(side, price, now)

    def get_history(self, side: str) -> List[PricePoint]:
        if side in self._history:
            return list(self._history[side])
        return []

    def get_history_count(self, side: str) -> int:
        if side in self._history:
            return len(self._history[side])
        return 0

    def get_current_price(self, side: str) -> float:
        if side in self._history and self._history[side]:
            return self._history[side][-1].price
        return 0.0

    def get_price_at(self, side: str, seconds_ago: float) -> Optional[float]:
        if side not in self._history:
            return None
        now = time.time()
        target_time = now - seconds_ago
        for point in self._history[side]:
            if point.timestamp >= target_time:
                return point.price
        return None

    def detect_flash_crash(self, side: Optional[str] = None) -> Optional[FlashCrashEvent]:
        sides_to_check = [side] if side else ["up", "down"]
        now = time.time()
        for s in sides_to_check:
            if s not in self._history:
                continue
            history = self._history[s]
            if len(history) < 2:
                continue
            current_price = history[-1].price
            old_price = None
            for point in history:
                if now - point.timestamp <= self.lookback_seconds:
                    old_price = point.price
                    break
            if old_price is None:
                continue
            drop = old_price - current_price
            if drop >= self.drop_threshold:
                return FlashCrashEvent(
                    side=s, old_price=old_price, new_price=current_price,
                    drop=drop, timestamp=now,
                )
        return None

    def detect_all_crashes(self) -> List[FlashCrashEvent]:
        events = []
        for side in ["up", "down"]:
            event = self.detect_flash_crash(side)
            if event:
                events.append(event)
        return events

    def clear(self, side: Optional[str] = None) -> None:
        if side:
            if side in self._history:
                self._history[side].clear()
        else:
            for s in self._history:
                self._history[s].clear()

    def get_price_range(self, side: str, seconds: float) -> tuple:
        if side not in self._history:
            return (0.0, 0.0)
        now = time.time()
        cutoff = now - seconds
        prices = [p.price for p in self._history[side] if p.timestamp >= cutoff]
        if not prices:
            return (0.0, 0.0)
        return (min(prices), max(prices))

    def get_volatility(self, side: str, seconds: float) -> float:
        min_price, max_price = self.get_price_range(side, seconds)
        return max_price - min_price
