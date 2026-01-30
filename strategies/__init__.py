from fastapi import FastAPI
import yfinance as yf
import pandas as pd

app = FastAPI(title="Trading Backend API")

# Symbols mapping
SYMBOL_MAP = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "FINNIFTY": "FINNIFTY.NS"  # adjust Yahoo Finance symbol if needed
}


def safe_float(val):
    """Convert value to float or None if NaN/Inf"""
    if pd.isna(val) or val is None:
        return None
    val = float(val)
    if val != val or val == float("inf") or val == float("-inf"):
        return None
    return val


def fetch_data(yf_symbol: str, interval="5m", period="7d"):
    """
    Fetch candle data from Yahoo Finance.
    Fallback to daily candles if 5-min data is empty or insufficient.
    """
    df = yf.Ticker(yf_symbol).history(period=period, interval=interval)

    # Fallback to daily if empty or too few rows
    if df.empty or len(df) < 50:
        df = yf.Ticker(yf_symbol).history(period="50d", interval="1d")

    if df.empty or "Close" not in df.columns:
        return None

    # For intraday, filter trading hours
    if interval != "1d":
        try:
            df = df.tz_convert("Asia/Kolkata")
            df = df.between_time("09:15", "15:30")
        except Exception:
            pass  # skip if tz_convert fails

    df = df.copy()

    # ================= INDICATORS =================
    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA21"] = df["Close"].ewm(span=21).mean()

    # VWAP
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    df["VWAP"] = (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()

    # MACD
    ema12 = df["Close"].ewm(span=12).mean()
    ema26 = df["Close"].ewm(span=26).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9).mean()
    df["MACD_HIST"] = df["MACD"] - df["MACD_SIGNAL"]

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    sma = df["Close"].rolling(20).mean()
    std = df["Close"].rolling(20).std()
    df["BB_UPPER"] = sma + 2 * std
    df["BB_LOWER"] = sma - 2 * std
    # =================================================

    return df


@app.get("/")
def home():
    return {"status": "Trading backend running"}


@app.get("/chart/{symbol}")
def chart_symbol(symbol: str):
    yf_symbol = SYMBOL_MAP.get(symbol.upper())
    if not yf_symbol:
        return {"data": [], "error": "Invalid symbol"}

    df = fetch_data(yf_symbol)
    if df is None or df.empty:
        return {"data": [], "error": "No usable data for this symbol"}

    # For intraday, show only last day
    if "date" not in df.columns:
        df["date"] = df.index.date
        last_day = df["date"].iloc[-1]
        df = df[df["date"] == last_day]

    data = []
    for t, r in df.iterrows():
        data.append({
            "time": t.isoformat(),
            "open": safe_float(r.get("Open")),
            "high": safe_float(r.get("High")),
            "low": safe_float(r.get("Low")),
            "close": safe_float(r.get("Close")),
            "ema9": safe_float(r.get("EMA9")),
            "ema21": safe_float(r.get("EMA21")),
            "vwap": safe_float(r.get("VWAP")),
            "macd": safe_float(r.get("MACD")),
            "macdSignal": safe_float(r.get("MACD_SIGNAL")),
            "macdHist": safe_float(r.get("MACD_HIST")),
            "rsi": safe_float(r.get("RSI")),
            "bbUpper": safe_float(r.get("BB_UPPER")),
            "bbLower": safe_float(r.get("BB_LOWER")),
            "volume": safe_float(r.get("Volume")),
        })
    return {"data": data}


@app.get("/chart/{symbol}/recent")
def chart_recent(symbol: str, interval: str = "5m", limit: int = 50):
    """
    Return last `limit` candles for a symbol.
    interval: "5m" or "1d"
    """
    yf_symbol = SYMBOL_MAP.get(symbol.upper())
    if not yf_symbol:
        return {"data": [], "error": "Invalid symbol"}

    df = fetch_data(yf_symbol, interval=interval, period="7d")
    if df is None or df.empty:
        return {"data": [], "error": "No usable data for this symbol"}

    df = df.tail(limit)

    data = []
    for t, r in df.iterrows():
        data.append({
            "time": t.isoformat(),
            "open": safe_float(r.get("Open")),
            "high": safe_float(r.get("High")),
            "low": safe_float(r.get("Low")),
            "close": safe_float(r.get("Close")),
            "ema9": safe_float(r.get("EMA9")),
            "ema21": safe_float(r.get("EMA21")),
            "vwap": safe_float(r.get("VWAP")),
            "macd": safe_float(r.get("MACD")),
            "macdSignal": safe_float(r.get("MACD_SIGNAL")),
            "macdHist": safe_float(r.get("MACD_HIST")),
            "rsi": safe_float(r.get("RSI")),
            "bbUpper": safe_float(r.get("BB_UPPER")),
            "bbLower": safe_float(r.get("BB_LOWER")),
            "volume": safe_float(r.get("Volume")),
        })
    return {"data": data}


@app.get("/data")
def all_data():
    """Return latest candle + indicators for all symbols"""
    result = {}
    for symbol, yf_symbol in SYMBOL_MAP.items():
        df = fetch_data(yf_symbol)
        if df is None or df.empty:
            result[symbol] = {"error": "No usable data"}
            continue

        last = df.iloc[-1]
        result[symbol] = {
            "close": safe_float(last["Close"]),
            "ema9": safe_float(last.get("EMA9")),
            "ema21": safe_float(last.get("EMA21")),
            "vwap": safe_float(last.get("VWAP")),
            "macd": safe_float(last.get("MACD")),
            "macdSignal": safe_float(last.get("MACD_SIGNAL")),
            "macdHist": safe_float(last.get("MACD_HIST")),
            "rsi": safe_float(last.get("RSI")),
            "bbUpper": safe_float(last.get("BB_UPPER")),
            "bbLower": safe_float(last.get("BB_LOWER")),
            "volume": safe_float(last.get("Volume")),
        }
    return result
