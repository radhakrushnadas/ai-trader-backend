def ema_vwap_strategy(row, prev_row=None):
    """
    row: latest candle (Series)
    prev_row: previous candle (Series)
    """

    if row is None or prev_row is None:
        return {"signal": "NONE", "confidence": 0, "reason": "Insufficient data"}

    # BUY CONDITIONS
    buy_conditions = [
        row["EMA9"] > row["EMA21"],
        row["Close"] > row["VWAP"],
        row["RSI"] > 50,
        row["MACD_HIST"] > prev_row["MACD_HIST"],
    ]

    # SELL CONDITIONS
    sell_conditions = [
        row["EMA9"] < row["EMA21"],
        row["Close"] < row["VWAP"],
        row["RSI"] < 50,
        row["MACD_HIST"] < prev_row["MACD_HIST"],
    ]

    if all(buy_conditions):
        return {
            "signal": "BUY",
            "confidence": 80,
            "reason": "EMA9>EMA21, price above VWAP, RSI bullish, MACD rising"
        }

    if all(sell_conditions):
        return {
            "signal": "SELL",
            "confidence": 80,
            "reason": "EMA9<EMA21, price below VWAP, RSI bearish, MACD falling"
        }

    return {"signal": "NONE", "confidence": 0, "reason": "Conditions not met"}
