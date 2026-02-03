from fastapi import FastAPI
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import math

app = FastAPI()

# ================= CONFIG =================

START_CAPITAL = 100000

INDEX_MAP = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS"
}

STRIKE_STEP = {
    "NIFTY": 50,
    "FINNIFTY": 50,
    "BANKNIFTY": 100
}

# ================= UTIL =================

def safe(v):
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except:
        return None

def nearest_strike(price, step):
    return int(round(price / step) * step)

def next_expiry():
    today = datetime.now()
    days = (3 - today.weekday()) % 7
    if days == 0:
        days = 7
    return (today + timedelta(days=days)).strftime("%d-%b-%Y")

# ================= INDICATORS =================

def add_indicators(df):
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA21"] = df["Close"].ewm(span=21).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + rs))
    return df

# ================= STRATEGY =================

def ema_signal(row, prev):
    if prev is None:
        return "NONE"
    if prev["EMA9"] < prev["EMA21"] and row["EMA9"] > row["EMA21"]:
        return "BUY"
    if prev["EMA9"] > prev["EMA21"] and row["EMA9"] < row["EMA21"]:
        return "SELL"
    return "NONE"

def rsi_filter(row):
    if row["RSI"] is None:
        return "NONE"
    if row["RSI"] < 30:
        return "BUY"
    if row["RSI"] > 70:
        return "SELL"
    return "NONE"

def final_signal(row, prev):
    s1 = ema_signal(row, prev)
    s2 = rsi_filter(row)
    return s1 if s1 == s2 else "NONE"

# ================= OPTION LOGIC =================

def option_premium(spot):
    return max(40, spot * 0.004)

def option_delta(option_type):
    return 0.55 if option_type == "CE" else -0.55

def pick_strike(spot, step, mode):
    atm = nearest_strike(spot, step)
    if mode == "ATM":
        return atm
    if mode == "ITM":
        return atm - step
    if mode == "OTM":
        return atm + step
    return atm

def start_option_trade(signal, spot, symbol, mode="ATM"):
    step = STRIKE_STEP[symbol]
    opt_type = "CE" if signal == "BUY" else "PE"
    strike = pick_strike(spot, step, mode)
    premium = option_premium(spot)
    delta = option_delta(opt_type)

    if abs(delta) < 0.4:
        return None  # Delta filter

    return {
        "symbol": symbol,
        "expiry": next_expiry(),
        "strike": strike,
        "type": opt_type,
        "entry": round(premium, 2),
        "sl": round(premium * 0.7, 2),
        "target": round(premium * 1.5, 2),
        "trail": False,
        "status": "OPEN"
    }

def manage_trade(trade, premium):
    entry = trade["entry"]

    if not trade["trail"] and premium >= entry * 1.1:
        trade["sl"] = entry
        trade["trail"] = True

    if trade["trail"]:
        trade["sl"] = max(trade["sl"], premium * 0.95)

    if premium <= trade["sl"]:
        trade["status"] = "SL HIT"

    if premium >= trade["target"]:
        trade["status"] = "TARGET HIT"

    return trade

# ================= DATA FETCH =================

def fetch(symbol, interval="5m", period="7d"):
    yf_symbol = INDEX_MAP[symbol]
    try:
        df = yf.download(yf_symbol, interval=interval, period=period, progress=False)
        if df.empty:
            raise ValueError("Empty data")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        return df, "LIVE"
    except Exception as e:
        # Fallback to last available daily candle
        df = yf.download(yf_symbol, interval="1d", period="5d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        return df, "MARKET CLOSED"

# ================= API =================

@app.get("/")
def health():
    return {"status": "ok"}

@app.get("/chart/{symbol}")
def chart(symbol: str):
    symbol = symbol.upper()
    if symbol not in INDEX_MAP:
        return {"error": "Only index options supported"}

    df5, status5 = fetch(symbol, "5m")
    df15, status15 = fetch(symbol, "15m")

    market_status = "LIVE" if status5 == "LIVE" and status15 == "LIVE" else "MARKET CLOSED"

    df5 = add_indicators(df5)
    df15 = add_indicators(df15)

    capital = START_CAPITAL
    trade = None
    journal = []
    candles = []

    for i in range(1, min(len(df5), len(df15))):
        r5, p5 = df5.iloc[i], df5.iloc[i-1]
        r15, p15 = df15.iloc[i], df15.iloc[i-1]

        row5 = {"EMA9": safe(r5["EMA9"]), "EMA21": safe(r5["EMA21"]), "RSI": safe(r5["RSI"])}
        prev5 = {"EMA9": safe(p5["EMA9"]), "EMA21": safe(p5["EMA21"]), "RSI": safe(p5["RSI"])}

        row15 = {"EMA9": safe(r15["EMA9"]), "EMA21": safe(r15["EMA21"]), "RSI": safe(r15["RSI"])}
        prev15 = {"EMA9": safe(p15["EMA9"]), "EMA21": safe(p15["EMA21"]), "RSI": safe(p15["RSI"])}

        sig5 = final_signal(row5, prev5)
        sig15 = final_signal(row15, prev15)

        signal = sig5 if sig5 == sig15 else "NONE"

        spot = safe(r5["Close"])
        premium = option_premium(spot)

        if trade is None and signal != "NONE":
            trade = start_option_trade(signal, spot, symbol, mode="ATM")

        if trade:
            trade = manage_trade(trade, premium)
            if trade["status"] != "OPEN":
                pnl = premium - trade["entry"]
                capital += pnl
                journal.append({**trade, "exit": round(premium, 2), "pnl": round(pnl, 2)})
                trade = None

        candles.append({
            "time": r5["Datetime"].isoformat(),
            "spot": spot,
            "premium": round(premium, 2),
            "signal": signal,
            "capital": round(capital, 2),
            "trade": trade
        })

    last_data_time = df5["Datetime"].iloc[-1].isoformat() if not df5.empty else None

    return {
        "symbol": symbol,
        "market_status": market_status,
        "last_data_time": last_data_time,
        "capital": round(capital, 2),
        "journal": journal,
        "candles": candles[-120:]
    }
