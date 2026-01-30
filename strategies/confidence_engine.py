def combine_signals(signals):
    buy = sum(1 for s in signals if s["signal"] == "BUY")
    sell = sum(1 for s in signals if s["signal"] == "SELL")

    if buy >= 2:
        return {
            "final_signal": "BUY",
            "strength": buy,
            "confidence": buy * 30,
            "reason": "Multiple strategies confirm BUY"
        }

    if sell >= 2:
        return {
            "final_signal": "SELL",
            "strength": sell,
            "confidence": sell * 30,
            "reason": "Multiple strategies confirm SELL"
        }

    return {
        "final_signal": "NONE",
        "strength": 0,
        "confidence": 0,
        "reason": "No strong confirmation"
    }
