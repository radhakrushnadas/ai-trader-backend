from fastapi import FastAPI, Query
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

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
    if prev is None: return "NONE"
    if prev["EMA9"] < prev["EMA21"] and row["EMA9"] > row["EMA21"]: return "BUY"
    if prev["EMA9"] > prev["EMA21"] and row["EMA9"] < row["EMA21"]: return "SELL"
    return "NONE"

def rsi_filter(row):
    if row["RSI"] is None: return "NONE"
    if row["RSI"] < 30: return "BUY"
    if row["RSI"] > 70: return "SELL"
    return "NONE"

def final_signal(row, prev):
    s1 = ema_signal(row, prev)
    s2 = rsi_filter(row)
    return s1 if s1 == s2 else "NONE"

# ================= OPTION LOGIC =================
def option_premium(spot): return max(40, spot * 0.004)
def option_delta(option_type): return 0.55 if option_type == "CE" else -0.55
def pick_strike(spot, step, mode):
    atm = nearest_strike(spot, step)
    if mode == "ATM": return atm
    if mode == "ITM": return atm - step
    if mode == "OTM": return atm + step
    return atm

def start_option_trade(signal, spot, symbol, mode="ATM"):
    step = STRIKE_STEP[symbol]
    opt_type = "CE" if signal == "BUY" else "PE"
    strike = pick_strike(spot, step, mode)
    premium = option_premium(spot)
    delta = option_delta(opt_type)
    if abs(delta) < 0.4: return None
    return {
        "symbol": symbol,
        "expiry": next_expiry(),
        "strike": strike,
        "type": opt_type,
        "entry": round(premium,2),
        "sl": round(premium*0.7,2),
        "target": round(premium*1.5,2),
        "trail": False,
        "status": "OPEN"
    }

def manage_trade(trade, premium):
    entry = trade["entry"]
    if not trade["trail"] and premium >= entry*1.1:
        trade["sl"] = entry
        trade["trail"] = True
    if trade["trail"]:
        trade["sl"] = max(trade["sl"], premium*0.95)
    if premium <= trade["sl"]:
        trade["status"] = "SL HIT"
    if premium >= trade["target"]:
        trade["status"] = "TARGET HIT"
    return trade

# ================= DATA =================
def fetch(symbol, interval, paper=False):
    yf_symbol = INDEX_MAP[symbol]
    if paper:  # Use fake data for testing when market is closed
        now = datetime.now()
        df = pd.DataFrame({
            "Datetime": [now - timedelta(minutes=i*5) for i in range(100)][::-1],
            "Close": [10000 + i*2 for i in range(100)]
        })
    else:
        df = yf.download(yf_symbol, interval=interval, period="7d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
    return df

# ================= API =================
@app.get("/")
def health():
    return {"status":"ok"}

@app.get("/chart/{symbol}")
def chart(symbol: str, paper: bool = Query(False)):
    symbol = symbol.upper()
    if symbol not in INDEX_MAP:
        return {"error":"Only index options supported"}

    df5 = add_indicators(fetch(symbol, "5m", paper=paper))
    df15 = add_indicators(fetch(symbol, "15m", paper=paper))

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

        signal = final_signal(row5, prev5) if final_signal(row5, prev5) == final_signal(row15, prev15) else "NONE"

        spot = safe(r5["Close"])
        premium = option_premium(spot)

        if trade is None and signal != "NONE":
            trade = start_option_trade(signal, spot, symbol)

        if trade:
            trade = manage_trade(trade, premium)
            if trade["status"] != "OPEN":
                pnl = premium - trade["entry"]
                capital += pnl
                journal.append({**trade, "exit": round(premium,2), "pnl": round(pnl,2)})
                trade = None

        candles.append({
            "time": r5["Datetime"].isoformat(),
            "spot": spot,
            "premium": round(premium,2),
            "signal": signal,
            "capital": round(capital,2),
            "trade": trade
        })

    return {
        "symbol": symbol,
        "capital": round(capital,2),
        "journal": journal,
        "candles": candles[-120:]
    }
