#!/usr/bin/env python3
"""
Ask Arbitrage Bot for Polymarket Up/Down 15-minute markets.

In binary markets, UP + DOWN always pays $1.00.
If best_ask(UP) + best_ask(DOWN) < $1.00, buying both guarantees profit.

Usage:
    python apps/arb_runner.py --coin ETH --size 5 --spread 0.02
"""

import os
import sys
import asyncio
import argparse
import logging
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import create_bot_from_env
from src.bot import OrderResult
from lib import MarketManager, Colors
from lib.terminal_utils import log, format_countdown

logger = logging.getLogger(__name__)


@dataclass
class ArbTrade:
    """Record of an arbitrage trade pair."""
    id: int
    up_ask: float
    down_ask: float
    ask_sum: float
    spread: float
    size: float
    timestamp: float
    up_order_ok: bool = False
    down_order_ok: bool = False

    @property
    def profit_per_pair(self) -> float:
        return self.spread * self.size

    @property
    def both_filled(self) -> bool:
        return self.up_order_ok and self.down_order_ok


class AskArbStrategy:
    def __init__(
        self,
        coin: str = "ETH",
        trade_size: float = 5.0,
        min_spread: float = 0.02,
        cooldown_seconds: float = 5.0,
        max_trades: int = 10,
        price_buffer: float = 0.01,
    ):
        self.coin = coin.upper()
        self.trade_size = trade_size
        self.min_spread = min_spread
        self.cooldown_seconds = cooldown_seconds
        self.max_trades = max_trades
        self.price_buffer = price_buffer  # Buy slightly above ask to ensure fill

        self.market = MarketManager(coin=self.coin, market_check_interval=30.0)
        self.bot = None
        self._running = False

        # State
        self.trades: List[ArbTrade] = []
        self.total_invested = 0.0
        self.total_guaranteed_return = 0.0
        self.last_trade_time = 0.0
        self.opportunities_seen = 0

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def total_profit(self) -> float:
        return sum(t.profit_per_pair for t in self.trades if t.both_filled)

    @property
    def can_trade(self) -> bool:
        if self.trade_count >= self.max_trades:
            return False
        if time.time() - self.last_trade_time < self.cooldown_seconds:
            return False
        return True

    async def run(self) -> None:
        self._running = True

        try:
            self.bot = create_bot_from_env()
            log(f"Trading bot initialized (gasless: {self.bot.config.use_gasless})", "success")
        except ValueError as e:
            log(f"Failed to initialize bot: {e}", "error")
            return

        @self.market.on_book_update
        async def handle_book(snapshot):
            up_ob = self.market.get_orderbook("up")
            down_ob = self.market.get_orderbook("down")

            if not up_ob or not down_ob:
                return

            ask_sum = up_ob.best_ask + down_ob.best_ask
            spread = 1.0 - ask_sum

            if spread >= self.min_spread:
                self.opportunities_seen += 1
                await self._handle_arb(up_ob.best_ask, down_ob.best_ask, ask_sum, spread)

        @self.market.on_market_change
        def handle_market_change(old_slug, new_slug):
            log(f"Market changed: {old_slug} -> {new_slug}", "info")

        log(f"Starting ask arbitrage for {self.coin}...", "info")
        log(f"Config: size=${self.trade_size}, min_spread=${self.min_spread}, buffer={self.price_buffer}, cooldown={self.cooldown_seconds}s", "info")
        log(f"Max trades: {self.max_trades} (bankroll protection)", "info")

        if not await self.market.start():
            log("Failed to start market manager", "error")
            return

        await self.market.wait_for_data(timeout=10.0)

        market = self.market.current_market
        if market:
            log(f"Monitoring: {market.question}", "success")

        try:
            while self._running:
                await asyncio.sleep(1.0)
                self._print_status()
        except KeyboardInterrupt:
            log("\nStopping strategy...", "info")
        finally:
            await self.market.stop()
            self._print_summary()

    async def _handle_arb(self, up_ask: float, down_ask: float, ask_sum: float, spread: float) -> None:
        if not self.can_trade or not self.bot:
            return

        # Check if still profitable after adding price buffer
        actual_spread = spread - (2 * self.price_buffer)
        if actual_spread <= 0:
            log(f"Spread {spread:.4f} too small after buffer ({self.price_buffer*2:.4f}), skipping", "warning")
            return

        trade_id = self.trade_count + 1
        trade = ArbTrade(
            id=trade_id,
            up_ask=up_ask,
            down_ask=down_ask,
            ask_sum=ask_sum,
            spread=spread,
            size=self.trade_size,
            timestamp=time.time(),
        )

        log(
            f"ARB #{trade_id}: UP ask={up_ask:.4f} + DOWN ask={down_ask:.4f} = "
            f"{ask_sum:.4f} (spread: ${spread:.4f}, profit: ${trade.profit_per_pair:.4f})",
            "trade"
        )

        # Buy UP at ask price
        up_token = self.market.token_ids.get("up")
        down_token = self.market.token_ids.get("down")

        if not up_token or not down_token:
            log("Token IDs not available", "error")
            return

        # Place both orders together in a single batch request
        # Add price buffer to increase fill probability
        up_price = min(up_ask + self.price_buffer, 0.99)
        down_price = min(down_ask + self.price_buffer, 0.99)

        # Prepare both orders for batch submission
        orders = [
            {
                "token_id": up_token,
                "price": up_price,
                "size": self.trade_size,
                "side": "BUY",
            },
            {
                "token_id": down_token,
                "price": down_price,
                "size": self.trade_size,
                "side": "BUY",
            },
        ]

        # Send both orders together in a single batch request
        results = await self.bot.place_orders_batch(orders)
        
        # Extract results (assuming order matches input order)
        up_result = results[0] if len(results) > 0 else OrderResult(success=False, message="No result for UP order")
        down_result = results[1] if len(results) > 1 else OrderResult(success=False, message="No result for DOWN order")

        trade.up_order_ok = up_result.success
        trade.down_order_ok = down_result.success

        if up_result.success:
            log(f"  UP BUY filled: {self.trade_size} @ {up_price:.4f}", "success")
        else:
            log(f"  UP BUY failed: {up_result.message}", "error")

        if down_result.success:
            log(f"  DOWN BUY filled: {self.trade_size} @ {down_price:.4f}", "success")
        else:
            log(f"  DOWN BUY failed: {down_result.message}", "error")

        # Record trade
        self.trades.append(trade)
        self.last_trade_time = time.time()

        if trade.both_filled:
            actual_cost = (up_price + down_price) * self.trade_size
            actual_profit = (1.0 - up_price - down_price) * self.trade_size
            self.total_invested += actual_cost
            self.total_guaranteed_return += self.trade_size
            log(
                f"  ARB #{trade_id} COMPLETE: cost=${actual_cost:.4f}, "
                f"guaranteed return=${self.trade_size:.2f}, "
                f"profit=${actual_profit:.4f}",
                "success"
            )
        else:
            log(f"  ARB #{trade_id} PARTIAL - only one side filled", "warning")

    def _print_status(self) -> None:
        market = self.market.current_market
        if not market:
            return

        countdown = market.get_countdown_str()
        up_ob = self.market.get_orderbook("up")
        down_ob = self.market.get_orderbook("down")

        up_ask = up_ob.best_ask if up_ob else 1.0
        down_ask = down_ob.best_ask if down_ob else 1.0
        ask_sum = up_ask + down_ask
        spread = 1.0 - ask_sum

        spread_color = Colors.GREEN if spread >= self.min_spread else Colors.DIM

        print(
            f"\r[{countdown}] UP ask: {up_ask:.4f} | DOWN ask: {down_ask:.4f} | "
            f"Sum: {ask_sum:.4f} | {spread_color}Spread: ${spread:.4f}{Colors.RESET} | "
            f"Trades: {self.trade_count}/{self.max_trades} | "
            f"Profit: ${self.total_profit:.4f}",
            end="", flush=True
        )

    def _print_summary(self) -> None:
        print()
        log("=" * 60, "info")
        log("ARBITRAGE SESSION SUMMARY", "info")
        log("=" * 60, "info")
        log(f"Opportunities seen: {self.opportunities_seen}", "info")
        log(f"Trades executed: {self.trade_count}", "info")

        successful = sum(1 for t in self.trades if t.both_filled)
        partial = sum(1 for t in self.trades if not t.both_filled)
        log(f"Successful (both sides): {successful}", "success")
        if partial:
            log(f"Partial (one side only): {partial}", "warning")

        log(f"Total invested: ${self.total_invested:.4f}", "info")
        log(f"Guaranteed return: ${self.total_guaranteed_return:.2f}", "info")
        log(f"Total profit: ${self.total_profit:.4f}", "success")
        log("=" * 60, "info")


def main():
    parser = argparse.ArgumentParser(description="Ask Arbitrage Bot for Polymarket Up/Down markets")
    parser.add_argument("--coin", type=str, default="ETH", choices=["BTC", "ETH", "SOL", "XRP"])
    parser.add_argument("--size", type=float, default=5.0, help="Trade size in USDC per side (default: 5.0)")
    parser.add_argument("--spread", type=float, default=0.02, help="Min spread to trade (default: 0.02)")
    parser.add_argument("--cooldown", type=float, default=5.0, help="Seconds between trades (default: 5.0)")
    parser.add_argument("--max-trades", type=int, default=10, help="Max trades per session (default: 10)")
    parser.add_argument("--buffer", type=float, default=0.01, help="Price buffer above ask to ensure fill (default: 0.01)")
    args = parser.parse_args()

    strategy = AskArbStrategy(
        coin=args.coin,
        trade_size=args.size,
        min_spread=args.spread,
        cooldown_seconds=args.cooldown,
        max_trades=args.max_trades,
        price_buffer=args.buffer,
    )

    try:
        asyncio.run(strategy.run())
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()
