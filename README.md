# Polymarket Arbitrage Bot

> Automated trading bot for detecting and executing arbitrage opportunities on Polymarket binary markets (UP/DOWN 15-minute markets).

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue.svg)](https://github.com/vladmeeros/polymarket-arbitrage-bot)

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Safety & Disclaimer](#safety--disclaimer)

## Features

- **Real-time Arbitrage Detection**: Monitors orderbooks via WebSocket to detect when `UP + DOWN < $1.00`
- **Batch Order Execution**: Sends both orders simultaneously in a single API request
- **Gasless Trading**: Optional gasless trading support via Builder API
- **Market Monitoring**: Read-only monitoring tool for flash crashes and arbitrage opportunities
- **Risk Management**: Configurable trade limits, cooldown periods, and price buffers
- **Multi-Market Support**: Trade across BTC, ETH, SOL, XRP markets

## Installation

```bash
# Clone repository
git clone https://github.com/vladmeeros/polymarket-arbitrage-bot.git
cd polymarket-arbitrage-bot

# Install dependencies
pip install -r requirements.txt

# Optional: Install official client libraries
pip install py-clob-client py-builder-signing-sdk
```

## Configuration

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Then edit `.env` with your actual configuration. See `.env.example` for all available options.

```env
# Required
POLY_PRIVATE_KEY=your_private_key_here
POLY_PROXY_WALLET=0xYourSafeAddress
# or
POLY_SAFE_ADDRESS=0xYourSafeAddress

# Optional - Gasless Trading
POLY_BUILDER_API_KEY=your_builder_api_key
POLY_BUILDER_API_SECRET=your_builder_api_secret
POLY_BUILDER_API_PASSPHRASE=your_builder_passphrase

# Optional - CLOB Settings
POLY_CLOB_HOST=https://clob.polymarket.com
POLY_CLOB_CHAIN_ID=137
```

> **⚠️ Security**: Never commit your `.env` file to version control. The `.env.example` file is a template with all available configuration options.

## Usage

### Arbitrage Trading Bot

```bash
# Basic usage (ETH market, $5 per side, $0.02 min spread)
python apps/arb_runner.py

# Custom parameters
python apps/arb_runner.py --coin BTC --size 10 --spread 0.03 --cooldown 3

# Full options
python apps/arb_runner.py \
  --coin ETH \
  --size 5.0 \
  --spread 0.02 \
  --cooldown 5.0 \
  --max-trades 10 \
  --buffer 0.01
```

**Parameters:**
- `--coin`: Market to trade (BTC, ETH, SOL, XRP) - default: ETH
- `--size`: Trade size in USDC per side - default: 5.0
- `--spread`: Minimum spread to trade ($) - default: 0.02
- `--cooldown`: Seconds between trades - default: 5.0
- `--max-trades`: Maximum trades per session - default: 10
- `--buffer`: Price buffer above ask to ensure fill - default: 0.01

### Market Monitor (Read-Only)

```bash
# Basic monitoring
python apps/monitor.py --coin ETH

# Custom thresholds
python apps/monitor.py --coin BTC --drop 0.25 --arb 0.03
```

**Parameters:**
- `--coin`: Market to monitor (BTC, ETH, SOL, XRP)
- `--drop`: Flash crash drop threshold - default: 0.30
- `--arb`: Arbitrage threshold - default: 0.02

## How It Works

### Arbitrage Strategy

In Polymarket binary markets, **UP + DOWN always pays $1.00** at settlement. When `best_ask(UP) + best_ask(DOWN) < $1.00`, buying both guarantees profit.

**Example:**
```
UP ask:   $0.48
DOWN ask: $0.49
Total:    $0.97
Profit:   $0.03 per pair (guaranteed $1.00 return)
```

### Execution Flow

1. **Detection**: WebSocket monitors orderbooks in real-time
2. **Validation**: Checks if spread meets minimum threshold
3. **Batch Execution**: Creates and signs both orders, sends in single API request
4. **Result Tracking**: Monitors fill status and calculates actual profit

**Key Features:**
- **Batch Orders**: Both UP and DOWN orders sent together for atomic execution
- **Price Buffer**: Adds small premium above ask to increase fill probability
- **Cooldown**: Prevents over-trading and reduces risk
- **Max Trades**: Bankroll protection to limit exposure per session

## Project Structure

```
polymarket-arbitrage-bot/
├── apps/
│   ├── arb_runner.py      # Main arbitrage trading bot
│   ├── monitor.py         # Read-only market monitor
│   └── orderbook_viewer.py
├── lib/
│   ├── market_manager.py  # Market and orderbook management
│   ├── position_manager.py
│   ├── price_tracker.py   # Price history and flash crash detection
│   └── terminal_utils.py
├── src/
│   ├── bot.py             # Trading bot core
│   ├── client.py          # CLOB API client (with batch support)
│   ├── websocket_client.py # Real-time orderbook updates
│   ├── signer.py          # Order signing and authentication
│   └── utils.py
└── requirements.txt
```

## Safety & Disclaimer

### ⚠️ Important Warnings

- **Test with small sizes first** - Always start with minimal trade sizes
- **Ensure sufficient USDC balance** - Maintain adequate balance for trades and gas fees
- **Monitor initial trades** - Closely watch the first few trades to verify execution
- **Set appropriate limits** - Use `--max-trades` to limit exposure per session
- **Use cooldown periods** - Prevent rapid-fire trading
- **Understand the risks** - Trading involves financial risk; only trade what you can afford to lose

### Disclaimer

This software is provided "as is" without warranty. Trading cryptocurrencies and derivatives involves substantial risk of loss. The authors and contributors are not responsible for any financial losses. Use at your own risk.

## Contributing

Contributions are welcome! Please open an issue for major changes or submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Made with ❤️ for the Polymarket community**
