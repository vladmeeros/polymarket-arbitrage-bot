#!/bin/bash
# ============================================================
# Polymarket Arbitrage Bot - VPS Setup Script
# Run this on your Ubuntu 22.04 VPS after uploading the files
# ============================================================

set -e

echo "=========================================="
echo " Polymarket Bot - VPS Setup"
echo "=========================================="

# 1. Update system
echo "[1/6] Updating system..."
sudo apt update && sudo apt upgrade -y

# 2. Install Python 3.11 and essentials
echo "[2/6] Installing Python 3.11..."
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip git screen curl

# Make python3.11 the default python3
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 2>/dev/null || true

# 3. Create project directory and venv
echo "[3/6] Setting up virtual environment..."
cd ~/polymarket-arbitrage-bot
python3.11 -m venv .venv
source .venv/bin/activate

# 4. Install Python dependencies
echo "[4/6] Installing Python dependencies..."
pip install --upgrade pip
pip install py-clob-client py-builder-signing-sdk
pip install web3 eth-account cryptography pyyaml python-dotenv requests websockets

# 5. Verify installation
echo "[5/6] Verifying installation..."
python -c "
from py_clob_client.client import ClobClient
from py_builder_signing_sdk.config import BuilderConfig
print('py-clob-client OK')
print('py-builder-signing-sdk OK')
"
python -c "
from src.bot import TradingBot
print('TradingBot import OK')
"

# 6. Create systemd service for auto-restart
echo "[6/6] Creating systemd service..."
sudo tee /etc/systemd/system/polymarket-arb.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=Polymarket Arbitrage Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/polymarket-arbitrage-bot
Environment=PATH=/root/polymarket-arbitrage-bot/.venv/bin:/usr/bin
ExecStart=/root/polymarket-arbitrage-bot/.venv/bin/python apps/arb_runner.py --coin ETH --size 5 --spread 0.02 --max-trades 50
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo tee /etc/systemd/system/polymarket-flash.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=Polymarket Flash Crash Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/polymarket-arbitrage-bot
Environment=PATH=/root/polymarket-arbitrage-bot/.venv/bin:/usr/bin
ExecStart=/root/polymarket-arbitrage-bot/.venv/bin/python apps/flash_crash_runner.py --coin ETH --size 5 --drop 0.30
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo systemctl daemon-reload

echo ""
echo "=========================================="
echo " Setup Complete!"
echo "=========================================="
echo ""
echo " Commands:"
echo ""
echo "   ARBITRAGE BOT:"
echo "     Start:   sudo systemctl start polymarket-arb"
echo "     Stop:    sudo systemctl stop polymarket-arb"
echo "     Logs:    sudo journalctl -u polymarket-arb -f"
echo "     Enable:  sudo systemctl enable polymarket-arb"
echo ""
echo "   FLASH CRASH BOT:"
echo "     Start:   sudo systemctl start polymarket-flash"
echo "     Stop:    sudo systemctl stop polymarket-flash"
echo "     Logs:    sudo journalctl -u polymarket-flash -f"
echo "     Enable:  sudo systemctl enable polymarket-flash"
echo ""
echo "   MANUAL (screen session):"
echo "     screen -S arb"
echo "     source .venv/bin/activate"
echo "     python apps/arb_runner.py --coin ETH --size 5 --spread 0.02"
echo "     (Ctrl+A, D to detach)"
echo ""
echo "   MONITOR (alerts only, no trades):"
echo "     screen -S monitor"
echo "     source .venv/bin/activate"
echo "     python apps/monitor.py --coin ETH"
echo "     (Ctrl+A, D to detach)"
echo ""
