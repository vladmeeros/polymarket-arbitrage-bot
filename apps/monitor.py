#!/usr/bin/env python3
"""
Market Monitor - Alerts for Flash Crashes and Ask Arbitrage.

Read-only: no trades are executed. Alerts in terminal when opportunities appear.

Usage:
    python apps/monitor.py --coin ETH
    python apps/monitor.py --coin BTC --drop 0.25 --arb 0.03
"""

import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path

logging.getLogger("src.websocket_client").setLevel(logging.WARNING)

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import MarketManager, PriceTracker, Colors
from lib.terminal_utils import log, format_countdown, LogBuffer


class MarketMonitor:
    def __init__(
        self,
        coin: str = "ETH",
        drop_threshold: float = 0.30,
        lookback_seconds: int = 10,
        arb_threshold: float = 0.02,
    ):
        self.coin = coin.upper()
        self.drop_threshold = drop_threshold
        self.lookback_seconds = lookback_seconds
        self.arb_threshold = arb_threshold

        self.market = MarketManager(coin=self.coin, market_check_interval=30.0)
        self.prices = PriceTracker(
            lookback_seconds=lookback_seconds,
            drop_threshold=drop_threshold,
        )
        self.alerts = LogBuffer(max_size=15)
        self.running = False

        # Stats
        self.flash_crash_count = 0
        self.arb_count = 0
        self.best_arb_spread = 0.0

    async def run(self) -> None:
        self.running = True

        @self.market.on_book_update
        async def handle_book(snapshot):
            for side, token_id in self.market.token_ids.items():
                if token_id == snapshot.asset_id:
                    self.prices.record(side, snapshot.mid_price)
                    break

            # Check flash crash
            event = self.prices.detect_flash_crash()
            if event:
                self.flash_crash_count += 1
                self.alerts.add(
                    f"FLASH CRASH {event.side.upper()}: "
                    f"{event.old_price:.4f} -> {event.new_price:.4f} "
                    f"(drop: {event.drop:.4f}, {event.drop_percent:.1f}%)",
                    "trade"
                )

            # Check ask arbitrage
            up_ob = self.market.get_orderbook("up")
            down_ob = self.market.get_orderbook("down")
            if up_ob and down_ob:
                ask_sum = up_ob.best_ask + down_ob.best_ask
                if ask_sum < (1.0 - self.arb_threshold):
                    spread = 1.0 - ask_sum
                    if spread > self.best_arb_spread:
                        self.best_arb_spread = spread
                    self.arb_count += 1
                    self.alerts.add(
                        f"ARB OPPORTUNITY: UP ask={up_ob.best_ask:.4f} + "
                        f"DOWN ask={down_ob.best_ask:.4f} = {ask_sum:.4f} "
                        f"(profit: ${spread:.4f}/pair)",
                        "success"
                    )

        @self.market.on_market_change
        def handle_market_change(old_slug, new_slug):
            self.alerts.add(f"Market changed: {new_slug}", "info")
            self.prices.clear()

        self.alerts.add(f"Starting monitor for {self.coin}...", "info")
        self.alerts.add(
            f"Flash crash: drop >= {self.drop_threshold} in {self.lookback_seconds}s | "
            f"Arb: ask sum < {1.0 - self.arb_threshold:.2f}",
            "info"
        )

        if not await self.market.start():
            print(f"{Colors.RED}Failed to start market manager{Colors.RESET}")
            return

        await self.market.wait_for_data(timeout=5.0)

        market = self.market.current_market
        if market:
            self.alerts.add(f"Monitoring: {market.question}", "success")

        try:
            while self.running:
                self.render()
                await asyncio.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            await self.market.stop()

    def render(self) -> None:
        lines = []
        market = self.market.current_market
        ws_status = f"{Colors.GREEN}Connected{Colors.RESET}" if self.market.is_connected else f"{Colors.RED}Disconnected{Colors.RESET}"
        countdown = "--:--"
        if market:
            mins, secs = market.get_countdown()
            countdown = format_countdown(mins, secs)

        # Header
        lines.append(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        lines.append(
            f"{Colors.CYAN}MONITOR{Colors.RESET} | {self.coin} | "
            f"{ws_status} | Ends: {countdown}"
        )
        lines.append(f"{Colors.BOLD}{'='*80}{Colors.RESET}")

        if market:
            lines.append(f"Market: {market.question}")
            lines.append("")

        # Prices
        up_ob = self.market.get_orderbook("up")
        down_ob = self.market.get_orderbook("down")

        up_bid = up_ob.best_bid if up_ob else 0
        up_ask = up_ob.best_ask if up_ob else 1
        down_bid = down_ob.best_bid if down_ob else 0
        down_ask = down_ob.best_ask if down_ob else 1
        up_mid = up_ob.mid_price if up_ob else 0
        down_mid = down_ob.mid_price if down_ob else 0

        lines.append(f"  {Colors.GREEN}UP{Colors.RESET}   Bid: {up_bid:.4f}  Ask: {up_ask:.4f}  Mid: {up_mid:.4f}")
        lines.append(f"  {Colors.RED}DOWN{Colors.RESET} Bid: {down_bid:.4f}  Ask: {down_ask:.4f}  Mid: {down_mid:.4f}")
        lines.append("")

        # Arbitrage status
        ask_sum = up_ask + down_ask
        spread = 1.0 - ask_sum
        if spread > self.arb_threshold:
            arb_color = Colors.GREEN
            arb_status = f"ARBITRAGE AVAILABLE (+${spread:.4f}/pair)"
        elif spread > 0:
            arb_color = Colors.YELLOW
            arb_status = f"Small spread (+${spread:.4f}/pair)"
        else:
            arb_color = Colors.RED
            arb_status = f"No arb (asks sum: {ask_sum:.4f})"

        lines.append(f"  Ask Sum: {ask_sum:.4f}  |  {arb_color}{arb_status}{Colors.RESET}")

        # Flash crash detection
        up_vol = self.prices.get_volatility("up", self.lookback_seconds)
        down_vol = self.prices.get_volatility("down", self.lookback_seconds)
        lines.append(f"  {self.lookback_seconds}s Volatility: UP={up_vol:.4f}  DOWN={down_vol:.4f}")

        lines.append("")
        lines.append(f"{Colors.BOLD}{'-'*80}{Colors.RESET}")

        # Stats
        lines.append(
            f"  Flash Crashes: {self.flash_crash_count} | "
            f"Arb Opportunities: {self.arb_count} | "
            f"Best Arb Spread: ${self.best_arb_spread:.4f}"
        )

        lines.append(f"{Colors.BOLD}{'-'*80}{Colors.RESET}")

        # Alert log
        lines.append(f"{Colors.BOLD}Alerts:{Colors.RESET}")
        messages = self.alerts.get_messages()
        if messages:
            for msg in messages:
                lines.append(f"  {msg}")
        else:
            lines.append(f"  {Colors.DIM}Waiting for signals...{Colors.RESET}")

        lines.append(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        lines.append(f"{Colors.DIM}Press Ctrl+C to exit{Colors.RESET}")

        output = "\033[H\033[J" + "\n".join(lines)
        print(output, flush=True)


def main():
    parser = argparse.ArgumentParser(description="Market Monitor - Flash Crash & Arbitrage Alerts")
    parser.add_argument("--coin", type=str, default="ETH", choices=["BTC", "ETH", "SOL", "XRP"])
    parser.add_argument("--drop", type=float, default=0.30, help="Flash crash drop threshold (default: 0.30)")
    parser.add_argument("--lookback", type=int, default=10, help="Lookback window in seconds (default: 10)")
    parser.add_argument("--arb", type=float, default=0.02, help="Min arb spread to alert (default: 0.02)")
    args = parser.parse_args()

    monitor = MarketMonitor(
        coin=args.coin,
        drop_threshold=args.drop,
        lookback_seconds=args.lookback,
        arb_threshold=args.arb,
    )

    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()
