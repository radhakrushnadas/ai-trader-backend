from fastapi import FastAPI
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

app = FastAPI(title="AI Trader Backend")

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

def option_delta(opt_type):
    return 0.55 if opt_type == "CE" else -0.55

def pick_strike(spot, step):
    return nearest_strike(spot, step)

def start_option_trade(signal, spot, symbol):
    step = STRIKE_STEP[symbol]
    opt_type = "CE" if signal == "BUY" else "PE"
    strike = pick_strike(spot, step)
    premium = option_premium(spot)

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

def fetch(symbol, interval):
    yf_symbol = INDEX_MAP[symbol]

    try:
        df = yf.download(
            yf_symbol,
            interval=interval,
            period="7d",
            progress=False,
            threads=False
        )
    except:
        df = None

    data_mode = "LIVE"

    if df is None or df.empty:
        try:
            df = yf.download(
                yf_symbol,
                interval="1d",
                period="2d",
                progress=False,
                threads=False
            )
            data_mode = "LAST_DAY"
        except:
            return None, None, "NO DATA"

    if df is None or df.empty:
        return None, None, "NO DATA"

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    last_time = df.iloc[-1].get("Datetime") or df.iloc[-1].get("Date")

    return df, last_time, data_mode

def market_status(last_time):
    if last_time is None:
        return "NO DATA"
    if datetime.now() - last_time > timedelta(minutes=20):
        return "MARKET CLOSED"
    return "MARKET LIVE"

# ================= API =================

@app.get("/")
def root():
    return {"status": "AI Trader Backend Running"}

@app.get("/chart/{symbol}")
def chart(symbol: str):
    symbol = symbol.upper()
    if symbol not in INDEX_MAP:
        return {"error": "Invalid symbol"}

    df5, last5, mode5 = fetch(symbol, "5m")
    df15, last15, mode15 = fetch(symbol, "15m")

    if df5 is None or df15 is None:
        return {"error": "Yahoo Finance not responding"}

    df5 = add_indicators(df5)
    df15 = add_indicators(df15)

    status = market_status(last5)

    capital = START_CAPITAL
    trade = None
    journal = []
    candles = []

    for i in range(1, min(len(df5), len(df15))):
        r5, p5 = df5.iloc[i], df5.iloc[i - 1]
        r15, p15 = df15.iloc[i], df15.iloc[i - 1]

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
            trade = start_option_trade(signal, spot, symbol)

        if trade:
            trade = manage_trade(trade, premium)
            if trade["status"] != "OPEN":
                pnl = premium - trade["entry"]
                capital += pnl
                journal.append({**trade, "exit": round(premium, 2), "pnl": round(pnl, 2)})
                trade = None

        candles.append({
            "time": (r5.get("Datetime") or r5.get("Date")).isoformat(),
            "spot": spot,
            "premium": round(premium, 2),
            "signal": signal,
            "capital": round(capital, 2)
        })

    return {
        "symbol": symbol,
        "market_status": status,
        "data_mode": "LIVE" if status == "MARKET LIVE" else "LAST ONE DAY DATA",
        "last_data_time": last5.isoformat() if last5 else None,
        "capital": round(capital, 2),
        "journal": journal,
        "candles": candles[-120:]
    }
