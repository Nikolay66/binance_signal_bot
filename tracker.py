import json
from datetime import datetime
from binance.client import get_price

SIGNALS_FILE = "signals.json"


def save_signal(signal):
    try:
        with open(SIGNALS_FILE, "r", encoding="utf-8") as file:
            signals = json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):
        signals = []

    signals.append(signal)

    with open(SIGNALS_FILE, "w", encoding="utf-8") as file:
        json.dump(
            signals,
            file,
            ensure_ascii=False,
            indent=4
        )


def get_active_signals():
    try:
        with open(SIGNALS_FILE, "r", encoding="utf-8") as file:
            signals = json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):
        return []

    return [
        signal
        for signal in signals
        if signal.get("status") == "ACTIVE"
    ]


def get_statistics():
    with open("signals.json", "r", encoding="utf-8") as file:
        signals = json.load(file)

    total = len(signals)

    tp = sum(1 for signal in signals if signal.get("result") == "TP")
    sl = sum(1 for signal in signals if signal.get("result") == "SL")
    active = sum(1 for signal in signals if signal.get("status") == "ACTIVE")

    finished = tp + sl

    if finished > 0:
        win_rate = tp / finished * 100
    else:
        win_rate = 0

    total_duration = 0

    for signal in signals:
        if signal.get("result") in ["TP", "SL"]:
            signal_time = signal.get("signal_time")
            result_time = signal.get("result_time")

            if signal_time and result_time:
                start = datetime.strptime(
                    signal_time,
                    "%Y-%m-%d %H:%M:%S"
                )

                end = datetime.strptime(
                    result_time,
                    "%Y-%m-%d %H:%M:%S"
                )

                duration = (end - start).total_seconds()
                total_duration += duration

    if finished > 0:
        average_duration = total_duration / finished
    else:
        average_duration = 0

    finished_signals = [
        signal for signal in signals
        if signal.get("result") in ["TP", "SL"]
    ]

    finished_signals.sort(
        key=lambda x: x.get("result_time", ""),
        reverse=True
    )

    current_streak = 0
    current_streak_result = None

    if finished_signals:
        current_streak_result = finished_signals[0].get("result")

        for signal in finished_signals:
            if signal.get("result") == current_streak_result:
                current_streak += 1
            else:
                break

    score_statistics = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        score = signal.get("score")

        if score is None:
            continue

        if score not in score_statistics:
            score_statistics[score] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        if signal.get("result") == "TP":
            score_statistics[score]["tp"] += 1
            score_statistics[score]["r"] += signal.get(
                "risk_reward", 0
            )

        elif signal.get("result") == "SL":
            score_statistics[score]["sl"] += 1
            score_statistics[score]["r"] -= 1

    for score, data in score_statistics.items():
        finished_score = data["tp"] + data["sl"]

        if finished_score > 0:
            data["win_rate"] = (
                data["tp"] / finished_score * 100
            )
        else:
            data["win_rate"] = 0

    score_direction_statistics = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        score = signal.get("score")
        direction = signal.get("signal")

        if score is None or direction not in ["LONG", "SHORT"]:
            continue

        if score not in score_direction_statistics:
            score_direction_statistics[score] = {
                "LONG": {
                    "tp": 0,
                    "sl": 0,
                    "r": 0
                },
                "SHORT": {
                    "tp": 0,
                    "sl": 0,
                    "r": 0
                }
            }

        data = score_direction_statistics[score][direction]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for score, directions in score_direction_statistics.items():
        for direction, data in directions.items():
            finished_direction = data["tp"] + data["sl"]

            if finished_direction > 0:
                data["win_rate"] = (
                    data["tp"] / finished_direction * 100
                )
            else:
                data["win_rate"] = 0

    confidence_statistics = {
        "70-79": {
            "tp": 0,
            "sl": 0,
            "r": 0
        },
        "80-89": {
            "tp": 0,
            "sl": 0,
            "r": 0
        },
        "90-100": {
            "tp": 0,
            "sl": 0,
            "r": 0
        }
    }

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        confidence = signal.get("confidence")

        if confidence is None:
            continue

        if 70 <= confidence < 80:
            group = "70-79"

        elif 80 <= confidence < 90:
            group = "80-89"

        elif 90 <= confidence <= 100:
            group = "90-100"

        else:
            continue

        data = confidence_statistics[group]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for group, data in confidence_statistics.items():
        finished_confidence = data["tp"] + data["sl"]

        if finished_confidence > 0:
            data["win_rate"] = (
                data["tp"] / finished_confidence * 100
            )
        else:
            data["win_rate"] = 0

    trend_1h_statistics = {
        "LONG_UP": {
            "tp": 0,
            "sl": 0,
            "r": 0
        },
        "LONG_DOWN": {
            "tp": 0,
            "sl": 0,
            "r": 0
        },
        "SHORT_UP": {
            "tp": 0,
            "sl": 0,
            "r": 0
        },
        "SHORT_DOWN": {
            "tp": 0,
            "sl": 0,
            "r": 0
        }
    }

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        direction = signal.get("signal")
        trend_1h = signal.get("trend_1h")

        if direction not in ["LONG", "SHORT"]:
            continue

        if trend_1h not in ["UP", "DOWN"]:
            continue

        group = f"{direction}_{trend_1h}"

        data = trend_1h_statistics[group]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for group, data in trend_1h_statistics.items():
        finished_trend = data["tp"] + data["sl"]

        if finished_trend > 0:
            data["win_rate"] = (
                data["tp"] / finished_trend * 100
            )
        else:
            data["win_rate"] = 0
    long_tp = sum(
        1 for signal in signals
        if signal.get("signal") == "LONG"
        and signal.get("result") == "TP"
    )

    long_sl = sum(
        1 for signal in signals
        if signal.get("signal") == "LONG"
        and signal.get("result") == "SL"
    )

    short_tp = sum(
        1 for signal in signals
        if signal.get("signal") == "SHORT"
        and signal.get("result") == "TP"
    )

    short_sl = sum(
        1 for signal in signals
        if signal.get("signal") == "SHORT"
        and signal.get("result") == "SL"
    )

    long_finished = long_tp + long_sl
    short_finished = short_tp + short_sl

    long_win_rate = (
        long_tp / long_finished * 100
        if long_finished > 0
        else 0
    )

    short_win_rate = (
        short_tp / short_finished * 100
        if short_finished > 0
        else 0
    )

    active_long = sum(
        1 for signal in signals
        if signal.get("status") == "ACTIVE"
        and signal.get("signal") == "LONG"
    )

    active_short = sum(
        1 for signal in signals
        if signal.get("status") == "ACTIVE"
        and signal.get("signal") == "SHORT"
    )
    total_r = 0

    for signal in signals:
        if signal.get("result") == "TP":
            total_r += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            total_r -= 1
    gross_profit = 0
    gross_loss = 0

    for signal in signals:
        if signal.get("result") == "TP":
            gross_profit += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            gross_loss += 1

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = 0

    long_r = 0
    short_r = 0

    for signal in signals:
        result = signal.get("result")
        direction = signal.get("signal")

        if direction == "LONG":
            if result == "TP":
                long_r += signal.get("risk_reward", 0)
            elif result == "SL":
                long_r -= 1

        elif direction == "SHORT":
            if result == "TP":
                short_r += signal.get("risk_reward", 0)
            elif result == "SL":
                short_r -= 1

    tp_r_total = 0

    for signal in signals:
        if signal.get("result") == "TP":
            tp_r_total += signal.get("risk_reward", 0)

    average_tp_r = (
        tp_r_total / tp
        if tp > 0
        else 0
    )

    average_r_per_trade = (
        total_r / finished
        if finished > 0
        else 0
    )
    # Максимальная просадка
    # Считаем только завершённые сделки
    # и сортируем их по реальному времени закрытия.

    finished_signals = [
        signal
        for signal in signals
        if signal.get("result") in ("TP", "SL")
        and signal.get("result_time")
    ]

    finished_signals.sort(
        key=lambda signal: signal["result_time"]
    )

    # Максимальная просадка
    # Считаем только завершённые сделки
    # и сортируем их по реальному времени закрытия.

    finished_signals = [
        signal
        for signal in signals
        if signal.get("result") in ("TP", "SL")
        and signal.get("result_time")
    ]

    finished_signals.sort(
        key=lambda signal: signal["result_time"]
    )

    cumulative_r = 0
    peak_r = 0
    max_drawdown_r = 0

    for signal in finished_signals:

        result = signal.get("result")

        if result == "TP":
            cumulative_r += signal.get("risk_reward", 0)

        elif result == "SL":
            cumulative_r -= 1

        if cumulative_r > peak_r:
            peak_r = cumulative_r

        drawdown = peak_r - cumulative_r

        if drawdown > max_drawdown_r:
            max_drawdown_r = drawdown
    return {
        "total": total,
        "tp": tp,
        "sl": sl,
        "active": active,
        "finished": finished,
        "win_rate": win_rate,

        "long_tp": long_tp,
        "long_sl": long_sl,
        "long_win_rate": long_win_rate,

        "short_tp": short_tp,
        "short_sl": short_sl,
        "short_win_rate": short_win_rate,
        "total_r": round(total_r, 2),
        "profit_factor": round(profit_factor, 2),
        "average_duration": round(average_duration, 0),
        "current_streak": current_streak,
        "current_streak_result": current_streak_result,
        "average_tp_r": round(average_tp_r, 2),
        "average_r_per_trade": round(average_r_per_trade, 2),
        "long_r": round(long_r, 2),
        "short_r": round(short_r, 2),
        "active_long": active_long,
        "active_short": active_short,
        "max_drawdown_r": round(max_drawdown_r, 2),
        "score_statistics": score_statistics,
        "score_direction_statistics": score_direction_statistics,
        "confidence_statistics": confidence_statistics,
        "trend_1h_statistics": trend_1h_statistics
    }


def update_signal(index, status, result):
    try:
        with open(SIGNALS_FILE, "r", encoding="utf-8") as file:
            signals = json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):
        return

    signals[index]["status"] = status
    signals[index]["result"] = result

    # Время закрытия сигнала
    from datetime import datetime

    signals[index]["result_time"] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with open(SIGNALS_FILE, "w", encoding="utf-8") as file:
        json.dump(
            signals,
            file,
            ensure_ascii=False,
            indent=4
        )


def check_signal(signal):
    symbol = signal["symbol"]

    current_price = get_price(symbol)

    if signal["signal"] == "LONG":

        if current_price >= signal["take_profit"]:
            return "TP"

        if current_price <= signal["stop_loss"]:
            return "SL"

    elif signal["signal"] == "SHORT":

        if current_price <= signal["take_profit"]:
            return "TP"

        if current_price >= signal["stop_loss"]:
            return "SL"

    return None


def check_active_signals():
    try:
        with open(SIGNALS_FILE, "r", encoding="utf-8") as file:
            signals = json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):
        return

    changed = False

    for index, signal in enumerate(signals):

        if signal.get("status") != "ACTIVE":
            continue

        result = check_signal(signal)

        if result is None:
            continue

        update_signal(
            index,
            result,
            result
        )

        print(
            f"🎯 {signal['symbol']} — "
            f"{result}"
        )

        changed = True

    if changed:
        print("✅ Результаты сигналов обновлены.")


def has_active_signal(symbol, signal):
    active_signals = get_active_signals()

    for active_signal in active_signals:
        if (
            active_signal.get("symbol") == symbol
            and active_signal.get("signal") == signal
        ):
            return True

    return False


if __name__ == "__main__":
    check_active_signals()
