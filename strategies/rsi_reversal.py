def rsi_reversal_strategy(row, prev_row):
    if row is None or prev_row is None:
        return {"signal": "NONE", "confidence": 0, "reason": "Insufficient data"}

    # BUY reversal
    if prev_row["RSI"] < 30 and row["RSI"] > prev_row["RSI"]:
        return {
            "signal": "BUY",
            "confidence": 65,
            "reason": "RSI reversal from oversold"
        }

    # SELL reversal
    if prev_row["RSI"] > 70 and row["RSI"] < prev_row["RSI"]:
        return {
            "signal": "SELL",
            "confidence": 65,
            "reason": "RSI reversal from overbought"
        }

    return {"signal": "NONE", "confidence": 0, "reason": "RSI neutral"}
