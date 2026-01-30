def ema_crossover_strategy(row, prev_row):
    if row is None or prev_row is None:
        return {"signal": "NONE", "confidence": 0, "reason": "Insufficient data"}

    # BUY crossover
    if prev_row["EMA9"] < prev_row["EMA21"] and row["EMA9"] > row["EMA21"]:
        return {
            "signal": "BUY",
            "confidence": 70,
            "reason": "EMA9 crossed above EMA21"
        }

    # SELL crossover
    if prev_row["EMA9"] > prev_row["EMA21"] and row["EMA9"] < row["EMA21"]:
        return {
            "signal": "SELL",
            "confidence": 70,
            "reason": "EMA9 crossed below EMA21"
        }

    return {"signal": "NONE", "confidence": 0, "reason": "No crossover"}
