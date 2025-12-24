 Smart Money Strategy Bot

Automated Futures trading bot using 5-minute scalping and 1-hour trend confirmation, implementing Smart Money concepts with real-time Telegram alerts.

⸻

Table of Contents
	•	Features
	•	Requirements
	•	Installation
	•	Configuration
	•	Usage
	•	Strategy Details
	•	Smart Money Alerts
	•	License

⸻

Features
	•	Real-time Binance Futures monitoring (USDT pairs by default).
	•	5-minute candlestick analysis with 1-hour higher timeframe trend confirmation.
	•	Smart Money concepts:
	•	Liquidity Sweep
	•	Wick Rejection
	•	Market Structure Shift (MSS/CHoCH)
	•	Fair Value Gap (FVG) Pullback
	•	Automatic stop-loss / take-profit calculation with 1:2 risk-reward ratio.
	•	Telegram alerts with setup ID and session info (London/New York).
	•	Duplicate alert prevention per setup.
	•	Works on Binance Testnet and Live account.

Configuration

All configuration is in settings.py:
	•	BINANCE_API_KEY / BINANCE_API_SECRET: Your Binance API credentials
	•	BINANCE_TESTNET: True for Testnet, False for Live
	•	QUOTE_ASSET: Default trading quote currency (USDT)
	•	SYMBOLS: Comma-separated list of symbols to monitor
	•	TIMEFRAME: Candlestick interval (5m)
	•	POLLING_INTERVAL_SECONDS: Bot polling interval in seconds

Strategy parameters (TDI, Bollinger Bands, MSS/FVG) can also be customized in settings.py.

Usage 

	•	The bot fetches real-time 5-minute data and 1-hour HTF data.
	•	Generates signals only if Smart Money conditions are met.
	•	Sends Telegram alerts with setup details: session, setup ID, entry, SL, TP.

Strategy Details

Timeframes
	•	LTF (Low Timeframe): 5-minute candlestick
	•	HTF (Higher Timeframe): 1-hour trend confirmation

Indicators
	•	TDI (Traders Dynamic Index): Fast/Slow MA on RSI
	•	Bollinger Bands: Price rejection detection
	•	Smart Money Concepts: MSS/CHoCH, Liquidity Sweep, FVG Pullback

Risk Management
	•	Stop-Loss (SL) based on liquidity sweep
	•	Take-Profit (TP) = 2 × risk
	•	Risk per trade can be set in settings.py

⸻

Smart Money Alerts

Example Telegram alert format:

🧠 SMART MONEY SETUP CONFIRMED
Pair: BTCUSDT
Direction: BUY
🕒 Session: LONDON
Setup ID: BUY_LONDON_202512221200

📍 Entry: 30000
🛑 Stop Loss: 29800
🎯 Take Profit: 30400

HTF (1H):
✔ Liquidity Sweep
✔ Wick Rejection
✔ EMA Trend: BULL