import json
import os
import shutil
import threading
import time
from datetime import datetime
from binance.client import get_price, get_klines_since

SIGNALS_FILE = "signals.json"
TS_FORMAT = "%Y-%m-%d %H:%M:%S"
MINUTE_MS = 60_000

# Один замок на все операции с файлом: save_signal (поток сканера) и
# check_active_signals (поток проверки) раньше могли затереть друг друга.
_file_lock = threading.RLock()


def _read_signals():
    try:
        with open(SIGNALS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except FileNotFoundError:
        return []

    except json.JSONDecodeError:
        # не затираем повреждённый файл молча - сохраняем копию
        backup = f"{SIGNALS_FILE}.corrupt-{int(time.time())}"
        try:
            shutil.copy(SIGNALS_FILE, backup)
            print(f"⚠️ {SIGNALS_FILE} повреждён, копия: {backup}")
        except OSError:
            pass
        return []


def _write_signals(signals):
    # атомарная запись: сначала временный файл, потом замена
    tmp_name = SIGNALS_FILE + ".tmp"

    with open(tmp_name, "w", encoding="utf-8") as file:
        json.dump(
            signals,
            file,
            ensure_ascii=False,
            indent=4
        )

    os.replace(tmp_name, SIGNALS_FILE)


def save_signal(signal):
    with _file_lock:
        signals = _read_signals()
        signals.append(signal)
        _write_signals(signals)


def get_active_signals():
    with _file_lock:
        signals = _read_signals()

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

    if finished < 20:
        reliability = "🔴 Мало данных"
    elif finished < 50:
        reliability = "🟡 Предварительная статистика"
    elif finished < 100:
        reliability = "🟠 Умеренный объём данных"
    else:
        reliability = "🟢 Достаточный объём данных"

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
        reverse=False
    )

    # Статистика сигналов по часовому тренду BTC
    btc_trend_stats = {}

    for signal in finished_signals:
        btc_trend = signal.get("btc_trend_1h", "UNKNOWN")
        direction = signal.get("signal")

        if btc_trend not in btc_trend_stats:
            btc_trend_stats[btc_trend] = {
                "LONG": {"TP": 0, "SL": 0, "R": 0},
                "SHORT": {"TP": 0, "SL": 0, "R": 0},
            }

        if direction not in ["LONG", "SHORT"]:
            continue

        result = signal.get("result")

        if result == "TP":
            btc_trend_stats[btc_trend][direction]["TP"] += 1
            btc_trend_stats[btc_trend][direction]["R"] += (
                signal.get("risk_reward", 0)
            )

        elif result == "SL":
            btc_trend_stats[btc_trend][direction]["SL"] += 1
            btc_trend_stats[btc_trend][direction]["R"] -= 1

    btc_trend_text = "\n\n📊 СТАТИСТИКА ПО ТРЕНДУ BTC (1H)\n"

    for btc_trend, directions in btc_trend_stats.items():
        btc_trend_text += f"\n₿ BTC: {btc_trend}\n"

        for direction, data in directions.items():
            finished_btc = data["TP"] + data["SL"]

            if finished_btc > 0:
                win_rate_btc = data["TP"] / finished_btc * 100
            else:
                win_rate_btc = 0

            btc_trend_text += (
                f"{'🟢' if direction == 'LONG' else '🔴'} {direction}: "
                f"TP {data['TP']} | SL {data['SL']} | "
                f"WR {win_rate_btc:.1f}% | "
                f"R {data['R']:+.2f}\n"
            )

    # Статистика сигналов по часовому тренду самой монеты
    coin_trend_stats = {}

    for signal in finished_signals:
        coin_trend = signal.get("trend_1h", "UNKNOWN")
        direction = signal.get("signal")

        if coin_trend not in coin_trend_stats:
            coin_trend_stats[coin_trend] = {
                "LONG": {"TP": 0, "SL": 0, "R": 0},
                "SHORT": {"TP": 0, "SL": 0, "R": 0},
            }

        if direction not in ["LONG", "SHORT"]:
            continue

        result = signal.get("result")

        if result == "TP":
            coin_trend_stats[coin_trend][direction]["TP"] += 1
            coin_trend_stats[coin_trend][direction]["R"] += (
                signal.get("risk_reward", 0)
            )

        elif result == "SL":
            coin_trend_stats[coin_trend][direction]["SL"] += 1
            coin_trend_stats[coin_trend][direction]["R"] -= 1

    coin_trend_text = "\n\n📊 СТАТИСТИКА ПО ТРЕНДУ МОНЕТЫ (1H)\n"

    for coin_trend, directions in coin_trend_stats.items():
        coin_trend_text += f"\n📈 Тренд монеты: {coin_trend}\n"

        for direction, data in directions.items():
            finished_coin = data["TP"] + data["SL"]

            if finished_coin > 0:
                win_rate_coin = data["TP"] / finished_coin * 100
            else:
                win_rate_coin = 0

            coin_trend_text += (
                f"{'🟢' if direction == 'LONG' else '🔴'} {direction}: "
                f"TP {data['TP']} | SL {data['SL']} | "
                f"WR {win_rate_coin:.1f}% | "
                f"R {data['R']:+.2f}\n"
            )

    current_streak = 0
    current_streak_result = None

    streak_signals = [
        signal
        for signal in signals
        if signal.get("result") in ("TP", "SL")
        and signal.get("result_time")
    ]

    streak_signals.sort(
        key=lambda signal: signal["result_time"]
    )

    if streak_signals:
        current_streak_result = streak_signals[-1].get("result")

        for signal in reversed(streak_signals):
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

    # Статистика Score отдельно для LONG и SHORT
    score_direction_stats = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        score = signal.get("score")
        direction = signal.get("signal")

        if score is None or direction not in ["LONG", "SHORT"]:
            continue

        if score not in score_direction_stats:
            score_direction_stats[score] = {
                "LONG": {"tp": 0, "sl": 0, "r": 0},
                "SHORT": {"tp": 0, "sl": 0, "r": 0},
            }

        data = score_direction_stats[score][direction]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    # Формирование отчёта по Score и направлению
    score_direction_text = "\n\n📊 SCORE: LONG vs SHORT\n"

    for score in sorted(score_direction_stats):
        score_direction_text += f"\n🎯 Score {score}\n"

        for direction in ["LONG", "SHORT"]:
            data = score_direction_stats[score][direction]
            finished_direction = data["tp"] + data["sl"]
            if finished_direction > 0:
                avg_r_direction = data["r"] / finished_direction
            else:
                avg_r_direction = 0

            if finished_direction > 0:
                win_rate_direction = (
                    data["tp"] / finished_direction * 100
                )
            else:
                win_rate_direction = 0

            score_direction_text += (
                f"{'🟢' if direction == 'LONG' else '🔴'} {direction}: "
                f"TP {data['tp']} | SL {data['sl']} | "
                f"WR {win_rate_direction:.1f}% | "
                f"R {data['r']:+.2f} | "
                f"Avg R {avg_r_direction:+.3f}\n"
            )

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

    # Статистика по Score, направлению и часовому тренду монеты
    score_trend_stats = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        score = signal.get("score")
        direction = signal.get("signal")
        trend = signal.get("trend_1h", "UNKNOWN")

        if score is None or direction not in ["LONG", "SHORT"]:
            continue

        key = (score, direction, trend)

        if key not in score_trend_stats:
            score_trend_stats[key] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_trend_stats[key]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    # Статистика по Score + тренду монеты + тренду BTC
    score_coin_btc_stats = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        score = signal.get("score")
        direction = signal.get("signal")
        coin_trend = signal.get("trend_1h", "UNKNOWN")
        btc_trend = signal.get("btc_trend_1h", "UNKNOWN")

        if score is None or direction not in ["LONG", "SHORT"]:
            continue

        key = (score, direction, coin_trend, btc_trend)

        if key not in score_coin_btc_stats:
            score_coin_btc_stats[key] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_coin_btc_stats[key]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    # Формирование отчёта по Score + трендам монеты и BTC
    score_coin_btc_text = "\n\n📊 SCORE + ТРЕНД МОНЕТЫ + BTC (1H)\n"

    for key in sorted(score_coin_btc_stats):
        score, direction, coin_trend, btc_trend = key
        data = score_coin_btc_stats[key]

        group_finished = data["tp"] + data["sl"]

        if group_finished == 0:
            continue

        group_win_rate = data["tp"] / group_finished * 100
        avg_r = data["r"] / group_finished

        emoji = "🟢" if direction == "LONG" else "🔴"

        score_coin_btc_text += (
            f"\n🎯 Score {score} | {emoji} {direction}\n"
            f"📈 Тренд монеты: {coin_trend} | BTC: {btc_trend}\n"
            f"TP {data['tp']} | SL {data['sl']} | "
            f"WR {group_win_rate:.1f}% | "
            f"R {data['r']:+.2f} | "
            f"Avg R {avg_r:+.3f}\n"
        )

    # Формирование отчёта по Score и тренду монеты
    score_trend_text = "\n\n📊 SCORE + ТРЕНД МОНЕТЫ (1H)\n"

    for key in sorted(score_trend_stats):
        score, direction, trend = key
        data = score_trend_stats[key]
        finished_trend = data["tp"] + data["sl"]

        if finished_trend > 0:
            win_rate_trend = data["tp"] / finished_trend * 100
            avg_r_trend = data["r"] / finished_trend
        else:
            win_rate_trend = 0
            avg_r_trend = 0

        emoji = "🟢" if direction == "LONG" else "🔴"

        score_trend_text += (
            f"\n🎯 Score {score} | {emoji} {direction} | "
            f"Тренд {trend}\n"
            f"TP {data['tp']} | SL {data['sl']} | "
            f"WR {win_rate_trend:.1f}% | "
            f"R {data['r']:+.2f} | "
            f"Avg R {avg_r_trend:+.3f}\n"
        )

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

    volume_statistics = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        volume_direction = signal.get("volume_direction")

        if volume_direction not in [
            "bullish",
            "bearish",
            "neutral"
        ]:
            continue

        if volume_direction not in volume_statistics:
            volume_statistics[volume_direction] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = volume_statistics[volume_direction]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for volume_direction, data in volume_statistics.items():
        finished_volume = data["tp"] + data["sl"]

        if finished_volume > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_volume
                * 100
            )
        else:
            data["win_rate"] = 0

    volume_strength_statistics = {}

    score_2_long_up_bullish_volume_statistics = {}

    score_2_bullish_direction_statistics = {}

    score_2_bullish_long_confidence_statistics = {}

    for signal in signals:

        if signal.get("result") not in ["TP", "SL"]:
            continue

        if signal.get("score") != 2:
            continue

        if signal.get("volume_direction") != "bullish":
            continue

        if signal.get("signal") != "LONG":
            continue

        confidence = signal.get("confidence")

        if confidence is None:
            continue

        if confidence < 80:
            confidence_range = "70-79"

        elif confidence < 90:
            confidence_range = "80-89"

        else:
            confidence_range = "90-100"

        if confidence_range not in score_2_bullish_long_confidence_statistics:
            score_2_bullish_long_confidence_statistics[confidence_range] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_2_bullish_long_confidence_statistics[confidence_range]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for confidence_range, data in score_2_bullish_long_confidence_statistics.items():

        finished_confidence = data["tp"] + data["sl"]

        if finished_confidence > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_confidence
                * 100
            )
        else:
            data["win_rate"] = 0

    score_2_bullish_long_reasons_statistics = {}

    for signal in signals:

        if signal.get("result") not in ["TP", "SL"]:
            continue

        if signal.get("score") != 2:
            continue

        if signal.get("volume_direction") != "bullish":
            continue

        if signal.get("signal") != "LONG":
            continue

        score_reasons = signal.get("score_reasons")

        if not score_reasons:
            continue

        reasons_key = " + ".join(score_reasons)

        if reasons_key not in score_2_bullish_long_reasons_statistics:
            score_2_bullish_long_reasons_statistics[reasons_key] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_2_bullish_long_reasons_statistics[reasons_key]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for reasons_key, data in score_2_bullish_long_reasons_statistics.items():

        finished_reasons = data["tp"] + data["sl"]

        if finished_reasons > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_reasons
                * 100
            )
        else:
            data["win_rate"] = 0

    for signal in signals:

        if signal.get("result") not in ["TP", "SL"]:
            continue

        if signal.get("score") != 2:
            continue

        if signal.get("volume_direction") != "bullish":
            continue

        direction = signal.get("signal")

        if direction not in ["LONG", "SHORT"]:
            continue

        if direction not in score_2_bullish_direction_statistics:
            score_2_bullish_direction_statistics[direction] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_2_bullish_direction_statistics[direction]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for direction, data in score_2_bullish_direction_statistics.items():

        finished_direction = data["tp"] + data["sl"]

        if finished_direction > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_direction
                * 100
            )
        else:
            data["win_rate"] = 0

    for signal in signals:

        if signal.get("result") not in ["TP", "SL"]:
            continue

        if signal.get("score") != 2:
            continue

        if signal.get("signal") != "LONG":
            continue

        if signal.get("trend_1h") != "UP":
            continue

        if signal.get("volume_direction") != "bullish":
            continue

        volume_balance = signal.get("volume_balance")

        if volume_balance is None:
            continue

        if volume_balance <= 1.20:
            volume_strength = "1.00-1.20"

        elif volume_balance <= 1.50:
            volume_strength = "1.20-1.50"

        elif volume_balance <= 2.00:
            volume_strength = "1.50-2.00"

        else:
            volume_strength = ">2.00"

        if volume_strength not in score_2_long_up_bullish_volume_statistics:
            score_2_long_up_bullish_volume_statistics[volume_strength] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_2_long_up_bullish_volume_statistics[volume_strength]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for volume_strength, data in score_2_long_up_bullish_volume_statistics.items():

        finished_bullish = data["tp"] + data["sl"]

        if finished_bullish > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_bullish
                * 100
            )
        else:
            data["win_rate"] = 0

    for signal in signals:

        if signal.get("result") not in ["TP", "SL"]:
            continue

        volume_balance = signal.get("volume_balance")

        if volume_balance is None:
            continue

        if volume_balance <= 1.20:
            volume_strength = "1.00-1.20"

        elif volume_balance <= 1.50:
            volume_strength = "1.20-1.50"

        elif volume_balance <= 2.00:
            volume_strength = "1.50-2.00"

        else:
            volume_strength = ">2.00"

        if volume_strength not in volume_strength_statistics:
            volume_strength_statistics[volume_strength] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = volume_strength_statistics[volume_strength]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for volume_strength, data in volume_strength_statistics.items():

        finished_strength = data["tp"] + data["sl"]

        if finished_strength > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_strength
                * 100
            )
        else:
            data["win_rate"] = 0

    score_confidence_statistics = {}

    score_volume_statistics = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        volume_direction = signal.get("volume_direction")
        score = signal.get("score")

        if volume_direction not in [
            "bullish",
            "bearish",
            "neutral"
        ]:
            continue

        key = (score, volume_direction)

        if key not in score_volume_statistics:
            score_volume_statistics[key] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_volume_statistics[key]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for key, data in score_volume_statistics.items():
        finished_score_volume = data["tp"] + data["sl"]

        if finished_score_volume > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_score_volume
                * 100
            )
        else:
            data["win_rate"] = 0

    score_volume_direction_statistics = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        volume_direction = signal.get("volume_direction")
        score = signal.get("score")
        direction = signal.get("signal")

        if volume_direction not in [
            "bullish",
            "bearish",
            "neutral"
        ]:
            continue

        if direction not in [
            "LONG",
            "SHORT"
        ]:
            continue

        key = (score, volume_direction, direction)

        if key not in score_volume_direction_statistics:
            score_volume_direction_statistics[key] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_volume_direction_statistics[key]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for key, data in score_volume_direction_statistics.items():
        finished_score_volume_direction = (
            data["tp"] + data["sl"]
        )

        if finished_score_volume_direction > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_score_volume_direction
                * 100
            )
        else:
            data["win_rate"] = 0

    score_volume_direction_trend_statistics = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        volume_direction = signal.get("volume_direction")
        score = signal.get("score")
        direction = signal.get("signal")
        trend_1h = signal.get("trend_1h")

        if volume_direction not in [
            "bullish",
            "bearish",
            "neutral"
        ]:
            continue

        if direction not in [
            "LONG",
            "SHORT"
        ]:
            continue

        if trend_1h not in [
            "UP",
            "DOWN"
        ]:
            continue

        key = (
            score,
            volume_direction,
            direction,
            trend_1h
        )

        if key not in score_volume_direction_trend_statistics:
            score_volume_direction_trend_statistics[key] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_volume_direction_trend_statistics[key]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for key, data in score_volume_direction_trend_statistics.items():
        finished_combination = data["tp"] + data["sl"]

        if finished_combination > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_combination
                * 100
            )
        else:
            data["win_rate"] = 0

    score_volume_direction_trend_confidence_statistics = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        volume_direction = signal.get("volume_direction")
        score = signal.get("score")
        direction = signal.get("signal")
        trend_1h = signal.get("trend_1h")
        confidence = signal.get("confidence")

        if volume_direction not in [
            "bullish",
            "bearish",
            "neutral"
        ]:
            continue

        if direction not in [
            "LONG",
            "SHORT"
        ]:
            continue

        if trend_1h not in [
            "UP",
            "DOWN"
        ]:
            continue

        if confidence is None:
            continue

        if confidence >= 90:
            confidence_group = "90-100"
        elif confidence >= 80:
            confidence_group = "80-89"
        elif confidence >= 70:
            confidence_group = "70-79"
        else:
            continue

        key = (
            score,
            volume_direction,
            direction,
            trend_1h,
            confidence_group
        )

        if key not in score_volume_direction_trend_confidence_statistics:
            score_volume_direction_trend_confidence_statistics[key] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_volume_direction_trend_confidence_statistics[key]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for key, data in score_volume_direction_trend_confidence_statistics.items():
        finished_combination = data["tp"] + data["sl"]

        if finished_combination > 0:
            data["win_rate"] = (
                data["tp"]
                / finished_combination
                * 100
            )
        else:
            data["win_rate"] = 0

    combination_quality_statistics = []

    for key, data in (
        score_volume_direction_trend_confidence_statistics.items()
    ):
        finished_trend_confidence = data["tp"] + data["sl"]

        if finished_trend_confidence == 0:
            continue

        combination_quality_statistics.append({
            "score": key[0],
            "volume_direction": key[1],
            "direction": key[2],
            "trend_1h": key[3],
            "confidence": key[4],
            "tp": data["tp"],
            "sl": data["sl"],
            "win_rate": data["win_rate"],
            "r": data["r"],
            "finished": finished_trend_confidence
        })

    combination_quality_statistics.sort(
        key=lambda item: item["r"],
        reverse=True
    )

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        score = signal.get("score")
        confidence = signal.get("confidence")

        if score is None or confidence is None:
            continue

        if 70 <= confidence < 80:
            confidence_group = "70-79"

        elif 80 <= confidence < 90:
            confidence_group = "80-89"

        elif 90 <= confidence <= 100:
            confidence_group = "90-100"

        else:
            continue

        if score not in score_confidence_statistics:
            score_confidence_statistics[score] = {}

        if confidence_group not in score_confidence_statistics[score]:
            score_confidence_statistics[score][confidence_group] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_confidence_statistics[
            score
        ][confidence_group]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for score, groups in score_confidence_statistics.items():

        for confidence_group, data in groups.items():

            finished_score_confidence = data["tp"] + data["sl"]

            if finished_score_confidence > 0:
                data["win_rate"] = (
                    data["tp"] / finished_score_confidence * 100
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
    duration_statistics = {
        "0-1h": {
            "tp": 0,
            "sl": 0,
            "r": 0
        },
        "1-3h": {
            "tp": 0,
            "sl": 0,
            "r": 0
        },
        "3-6h": {
            "tp": 0,
            "sl": 0,
            "r": 0
        },
        "6-12h": {
            "tp": 0,
            "sl": 0,
            "r": 0
        },
        "12h+": {
            "tp": 0,
            "sl": 0,
            "r": 0
        }
    }

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        signal_time = signal.get("signal_time")
        result_time = signal.get("result_time")

        if not signal_time or not result_time:
            continue

        start = datetime.strptime(
            signal_time,
            "%Y-%m-%d %H:%M:%S"
        )

        end = datetime.strptime(
            result_time,
            "%Y-%m-%d %H:%M:%S"
        )

        duration_hours = (
            end - start
        ).total_seconds() / 3600

        if duration_hours < 1:
            group = "0-1h"

        elif duration_hours < 3:
            group = "1-3h"

        elif duration_hours < 6:
            group = "3-6h"

        elif duration_hours < 12:
            group = "6-12h"

        else:
            group = "12h+"

        data = duration_statistics[group]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for group, data in duration_statistics.items():
        finished_duration = data["tp"] + data["sl"]

        if finished_duration > 0:
            data["win_rate"] = (
                data["tp"] / finished_duration * 100
            )
        else:
            data["win_rate"] = 0

    score_duration_statistics = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        score = signal.get("score")

        signal_time = signal.get("signal_time")
        result_time = signal.get("result_time")

        if score is None or not signal_time or not result_time:
            continue

        start = datetime.strptime(
            signal_time,
            "%Y-%m-%d %H:%M:%S"
        )

        end = datetime.strptime(
            result_time,
            "%Y-%m-%d %H:%M:%S"
        )

        duration_hours = (
            end - start
        ).total_seconds() / 3600

        if duration_hours < 1:
            duration_group = "0-1h"

        elif duration_hours < 3:
            duration_group = "1-3h"

        elif duration_hours < 6:
            duration_group = "3-6h"

        elif duration_hours < 12:
            duration_group = "6-12h"

        else:
            duration_group = "12h+"

        if score not in score_duration_statistics:
            score_duration_statistics[score] = {}

        if duration_group not in score_duration_statistics[score]:
            score_duration_statistics[score][duration_group] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_duration_statistics[score][duration_group]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for score, durations in score_duration_statistics.items():
        for duration_group, data in durations.items():

            finished_score_duration = (
                data["tp"] + data["sl"]
            )

            if finished_score_duration > 0:
                data["win_rate"] = (
                    data["tp"]
                    / finished_score_duration
                    * 100
                )
            else:
                data["win_rate"] = 0

    score_direction_duration_statistics = {}

    for signal in signals:
        if signal.get("result") not in ["TP", "SL"]:
            continue

        score = signal.get("score")
        direction = signal.get("signal")

        signal_time = signal.get("signal_time")
        result_time = signal.get("result_time")

        if (
            score is None
            or direction not in ["LONG", "SHORT"]
            or not signal_time
            or not result_time
        ):
            continue

        start = datetime.strptime(
            signal_time,
            "%Y-%m-%d %H:%M:%S"
        )

        end = datetime.strptime(
            result_time,
            "%Y-%m-%d %H:%M:%S"
        )

        duration_hours = (
            end - start
        ).total_seconds() / 3600

        if duration_hours < 1:
            duration_group = "0-1h"

        elif duration_hours < 3:
            duration_group = "1-3h"

        elif duration_hours < 6:
            duration_group = "3-6h"

        elif duration_hours < 12:
            duration_group = "6-12h"

        else:
            duration_group = "12h+"

        if score not in score_direction_duration_statistics:
            score_direction_duration_statistics[score] = {
                "LONG": {},
                "SHORT": {}
            }

        if (
            duration_group
            not in score_direction_duration_statistics[score][direction]
        ):
            score_direction_duration_statistics[score][direction][
                duration_group
            ] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = score_direction_duration_statistics[
            score
        ][direction][duration_group]

        if signal.get("result") == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)

        elif signal.get("result") == "SL":
            data["sl"] += 1
            data["r"] -= 1

    for score, directions in score_direction_duration_statistics.items():

        for direction, durations in directions.items():

            for duration_group, data in durations.items():

                finished_duration_group = data["tp"] + data["sl"]

                if finished_duration_group > 0:
                    data["win_rate"] = (
                        data["tp"] / finished_duration_group * 100
                    )
                else:
                    data["win_rate"] = 0
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

    recent_statistics = {}

    for period in [20, 50]:

        recent_signals = finished_signals[-period:]

        tp_count = 0
        sl_count = 0
        total_r_recent = 0

        for signal in recent_signals:

            if signal.get("result") == "TP":
                tp_count += 1
                total_r_recent += signal.get("risk_reward", 0)

            elif signal.get("result") == "SL":
                sl_count += 1
                total_r_recent -= 1

        finished__recent = tp_count + sl_count

        if finished__recent > 0:
            win_rate_recent = (
                tp_count
                / finished__recent
                * 100
            )
        else:
            win_rate_recent = 0

        recent_statistics[period] = {
            "tp": tp_count,
            "sl": sl_count,
            "finished": finished__recent,
            "win_rate": win_rate_recent,
            "r": total_r_recent
        }

    # Сравнение последних 20 сигналов с предыдущими 20
    last_20_signals = finished_signals[-20:]
    previous_20_signals = finished_signals[-40:-20]

    def calculate_period_stats(period_signals):
        tp = 0
        sl = 0
        total_r = 0

        for signal in period_signals:
            if signal.get("result") == "TP":
                tp += 1
                total_r += signal.get("risk_reward", 0)
            elif signal.get("result") == "SL":
                sl += 1
                total_r -= 1

        finished = tp + sl
        win_rate = tp / finished * 100 if finished else 0

        return {
            "tp": tp,
            "sl": sl,
            "finished": finished,
            "win_rate": win_rate,
            "r": total_r
        }

    recent_comparison = {
        "last_20": calculate_period_stats(last_20_signals),
        "previous_20": calculate_period_stats(previous_20_signals)
    }

    recent_direction_statistics = {}

    for period in [20, 50]:

        recent_signals = finished_signals[-period:]

        direction_stats = {
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

        for signal in recent_signals:

            direction = signal.get("signal")

            if direction not in ["LONG", "SHORT"]:
                continue

            if signal.get("result") == "TP":
                direction_stats[direction]["tp"] += 1
                direction_stats[direction]["r"] += (
                    signal.get("risk_reward", 0)
                )

            elif signal.get("result") == "SL":
                direction_stats[direction]["sl"] += 1
                direction_stats[direction]["r"] -= 1

        for direction, data in direction_stats.items():

            finished_direction_stats = data["tp"] + data["sl"]

            if finished_direction_stats > 0:
                data["win_rate"] = (
                    data["tp"]
                    / finished_direction_stats
                    * 100
                )
            else:
                data["win_rate"] = 0

        recent_direction_statistics[period] = direction_stats

    recent_trend_statistics = {}

    for period in [20, 50]:

        recent_signals = finished_signals[-period:]

        trend_stats = {}

        for signal in recent_signals:

            direction = signal.get("signal")
            trend_1h = signal.get("trend_1h")

            if direction not in ["LONG", "SHORT"]:
                continue

            if trend_1h not in ["UP", "DOWN"]:
                continue

            key = (direction, trend_1h)

            if key not in trend_stats:
                trend_stats[key] = {
                    "tp": 0,
                    "sl": 0,
                    "r": 0
                }

            data = trend_stats[key]

            if signal.get("result") == "TP":
                data["tp"] += 1
                data["r"] += signal.get("risk_reward", 0)

            elif signal.get("result") == "SL":
                data["sl"] += 1
                data["r"] -= 1

        for key, data in trend_stats.items():

            finished_trend_stats = data["tp"] + data["sl"]

            if finished_trend_stats > 0:
                data["win_rate"] = (
                    data["tp"]
                    / finished_trend_stats
                    * 100
                )
            else:
                data["win_rate"] = 0

        recent_trend_statistics[period] = trend_stats

    recent_score_trend_statistics = {}

    for period in [20, 50]:

        recent_signals = finished_signals[-period:]

        score_trend_stats = {}

        for signal in recent_signals:

            score = signal.get("score")
            direction = signal.get("signal")
            trend_1h = signal.get("trend_1h")

            if score is None:
                continue

            if direction not in ["LONG", "SHORT"]:
                continue

            if trend_1h not in ["UP", "DOWN"]:
                continue

            key = (
                score,
                direction,
                trend_1h
            )

            if key not in score_trend_stats:
                score_trend_stats[key] = {
                    "tp": 0,
                    "sl": 0,
                    "r": 0
                }

            data = score_trend_stats[key]

            if signal.get("result") == "TP":
                data["tp"] += 1
                data["r"] += signal.get("risk_reward", 0)

            elif signal.get("result") == "SL":
                data["sl"] += 1
                data["r"] -= 1

        for key, data in score_trend_stats.items():

            finished_score_trend_stats = data["tp"] + data["sl"]

            if finished_score_trend_stats > 0:
                data["win_rate"] = (
                    data["tp"]
                    / finished_score_trend_stats
                    * 100
                )
            else:
                data["win_rate"] = 0

        recent_score_trend_statistics[period] = (
            score_trend_stats
        )

    recent_score_trend_volume_statistics = {}

    for period in [20, 50]:

        recent_signals = finished_signals[-period:]

        score_trend_volume_stats = {}

        for signal in recent_signals:

            score = signal.get("score")
            direction = signal.get("signal")
            trend_1h = signal.get("trend_1h")
            volume_direction = signal.get("volume_direction")

            if score is None:
                continue

            if direction not in ["LONG", "SHORT"]:
                continue

            if trend_1h not in ["UP", "DOWN"]:
                continue

            if volume_direction not in ["bullish", "bearish", "neutral"]:
                continue

            key = (
                score,
                direction,
                trend_1h,
                volume_direction
            )

            if key not in score_trend_volume_stats:
                score_trend_volume_stats[key] = {
                    "tp": 0,
                    "sl": 0,
                    "r": 0
                }

            data = score_trend_volume_stats[key]

            if signal.get("result") == "TP":
                data["tp"] += 1
                data["r"] += signal.get("risk_reward", 0)

            elif signal.get("result") == "SL":
                data["sl"] += 1
                data["r"] -= 1

        for key, data in score_trend_volume_stats.items():

            finished_score_trend_volume_stats = data["tp"] + data["sl"]

            if finished_score_trend_volume_stats > 0:
                data["win_rate"] = (
                    data["tp"] / finished_score_trend_volume_stats * 100
                )
            else:
                data["win_rate"] = 0

        recent_score_trend_volume_statistics[period] = (
            score_trend_volume_stats
        )

    recent_problem_symbol_statistics = {}

    for period in [20, 50]:

        recent_signals = finished_signals[-period:]

        symbol_stats = {}

        for signal in recent_signals:

            score = signal.get("score")
            direction = signal.get("signal")
            trend_1h = signal.get("trend_1h")
            volume_direction = signal.get("volume_direction")
            symbol = signal.get("symbol")

            if score != 2:
                continue

            if direction != "LONG":
                continue

            if trend_1h != "UP":
                continue

            if volume_direction != "bullish":
                continue

            if not symbol:
                continue

            if symbol not in symbol_stats:
                symbol_stats[symbol] = {
                    "tp": 0,
                    "sl": 0,
                    "r": 0
                }

            data = symbol_stats[symbol]

            if signal.get("result") == "TP":
                data["tp"] += 1
                data["r"] += signal.get("risk_reward", 0)

            elif signal.get("result") == "SL":
                data["sl"] += 1
                data["r"] -= 1

        for symbol, data in symbol_stats.items():

            finished_symbol_stats = data["tp"] + data["sl"]

            if finished_symbol_stats > 0:
                data["win_rate"] = (
                    data["tp"] / finished_symbol_stats * 100
                )
            else:
                data["win_rate"] = 0

        recent_problem_symbol_statistics[period] = symbol_stats

    # Статистика по месяцам
    monthly_statistics = {}

    for signal in signals:
        result = signal.get("result")
        result_time = signal.get("result_time")

        if result not in ("TP", "SL") or not result_time:
            continue

        try:
            result_date = datetime.strptime(
                result_time,
                "%Y-%m-%d %H:%M:%S"
            )
        except (ValueError, TypeError):
            continue

        month_key = result_date.strftime("%Y-%m")

        if month_key not in monthly_statistics:
            monthly_statistics[month_key] = {
                "tp": 0,
                "sl": 0,
                "r": 0
            }

        data = monthly_statistics[month_key]

        if result == "TP":
            data["tp"] += 1
            data["r"] += signal.get("risk_reward", 0)
        else:
            data["sl"] += 1
            data["r"] -= 1

    for data in monthly_statistics.values():
        finished_month = data["tp"] + data["sl"]

        data["finished"] = finished_month
        data["win_rate"] = (
            data["tp"] / finished_month * 100
            if finished_month
            else 0
        )
        data["r"] = round(data["r"], 2)

    monthly_statistics = dict(sorted(monthly_statistics.items()))

    return {
        "total": total,
        "tp": tp,
        "sl": sl,
        "active": active,
        "btc_trend_text": btc_trend_text,
        "coin_trend_text": coin_trend_text,
        "score_direction_text": score_direction_text,
        "score_trend_text": score_trend_text,
        "score_coin_btc_text": score_coin_btc_text,
        "finished": finished,
        "win_rate": win_rate,
        "reliability": reliability,

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
        "volume_statistics": volume_statistics,
        "volume_strength_statistics": volume_strength_statistics,
        "score_2_long_up_bullish_volume_statistics": score_2_long_up_bullish_volume_statistics,
        "score_2_bullish_direction_statistics": score_2_bullish_direction_statistics,
        "score_2_bullish_long_confidence_statistics": score_2_bullish_long_confidence_statistics,
        "score_2_bullish_long_reasons_statistics": score_2_bullish_long_reasons_statistics,
        "score_volume_statistics": score_volume_statistics,
        "score_volume_direction_statistics": score_volume_direction_statistics,
        "score_volume_direction_trend_statistics": score_volume_direction_trend_statistics,
        "score_volume_direction_trend_confidence_statistics": (
            score_volume_direction_trend_confidence_statistics
        ),
        "combination_quality_statistics": (
            combination_quality_statistics
        ),
        "recent_statistics": recent_statistics,
        "monthly_statistics": monthly_statistics,
        "recent_comparison": recent_comparison,
        "recent_direction_statistics": recent_direction_statistics,
        "recent_trend_statistics": recent_trend_statistics,
        "recent_score_trend_statistics": (
            recent_score_trend_statistics
        ),
        "recent_score_trend_volume_statistics": (
            recent_score_trend_volume_statistics
        ),
        "recent_problem_symbol_statistics": (
            recent_problem_symbol_statistics
        ),
        "score_confidence_statistics": score_confidence_statistics,
        "trend_1h_statistics": trend_1h_statistics,
        "duration_statistics": duration_statistics,
        "score_duration_statistics": score_duration_statistics,
        "score_direction_duration_statistics": score_direction_duration_statistics
    }


def update_signal(index, status, result, extra=None):
    with _file_lock:
        signals = _read_signals()

        if index >= len(signals):
            return

        signals[index]["status"] = status
        signals[index]["result"] = result
        signals[index]["result_time"] = datetime.now().strftime(TS_FORMAT)

        if extra:
            signals[index].update(extra)

        _write_signals(signals)


def _first_candle_open(signal):
    """Открытие первой минутной свечи ПОСЛЕ создания сигнала (мс).

    Свечу, в которой появился сигнал, пропускаем: часть её диапазона
    была до входа."""
    created_ms = signal.get("created_ms")

    if not created_ms:
        # старые записи: signal_time - локальное время машины бота
        created_ms = int(
            datetime.strptime(signal["signal_time"], TS_FORMAT).timestamp()
            * 1000
        )

    return (int(created_ms) // MINUTE_MS + 1) * MINUTE_MS


def check_signal(signal):
    """Проверка сигнала по 1m-свечам (high/low), а не по цене раз в минуту.

    Если в одной свече задеты и SL, и TP - порядок неизвестен, считаем SL
    (консервативно).

    Возвращает словарь обновлений для записи сигнала (прогресс отслеживания,
    а при срабатывании ещё status/result/result_time/mfe_r/mae_r) или None,
    если данных пока нет."""
    symbol = signal["symbol"]
    is_long = signal["signal"] == "LONG"

    entry = signal["entry_price"]
    stop_loss = signal["stop_loss"]
    take_profit = signal["take_profit"]

    cursor = max(
        _first_candle_open(signal),
        int(signal.get("track_from_ms") or 0)
    )

    high_seen = signal.get("high_since_entry", entry)
    low_seen = signal.get("low_since_entry", entry)

    last_open = None
    outcome = None
    ambiguous = False
    hit_open = None

    while True:
        candles = get_klines_since(symbol, cursor)

        if not candles:
            break

        for candle in candles:
            open_ms = int(candle[0])
            high = float(candle[2])
            low = float(candle[3])

            last_open = open_ms
            high_seen = max(high_seen, high)
            low_seen = min(low_seen, low)

            if is_long:
                sl_hit = low <= stop_loss
                tp_hit = high >= take_profit
            else:
                sl_hit = high >= stop_loss
                tp_hit = low <= take_profit

            if sl_hit or tp_hit:
                outcome = "SL" if sl_hit else "TP"
                ambiguous = sl_hit and tp_hit
                hit_open = open_ms
                break

        if outcome is not None or len(candles) < 1500:
            break

        cursor = int(candles[-1][0]) + MINUTE_MS

    if last_open is None:
        return None

    updates = {
        "track_from_ms": last_open,
        "high_since_entry": high_seen,
        "low_since_entry": low_seen
    }

    if outcome is not None:
        risk = abs(entry - stop_loss)

        if is_long:
            mfe = (high_seen - entry) / risk
            mae = (entry - low_seen) / risk
        else:
            mfe = (entry - low_seen) / risk
            mae = (high_seen - entry) / risk

        updates.update({
            "status": outcome,
            "result": outcome,
            "result_time": datetime.fromtimestamp(
                hit_open / 1000
            ).strftime(TS_FORMAT),
            "ambiguous": ambiguous,
            "mfe_r": round(max(mfe, 0.0), 3),
            "mae_r": round(max(mae, 0.0), 3)
        })

    return updates


def check_active_signals():
    # 1) быстро читаем список, без сетевых запросов под замком
    with _file_lock:
        signals = _read_signals()

    pending = [
        (index, dict(signal))
        for index, signal in enumerate(signals)
        if signal.get("status") == "ACTIVE"
    ]

    if not pending:
        return

    # 2) сетевые запросы
    results = []

    for index, signal in pending:
        try:
            updates = check_signal(signal)

        except Exception as error:
            print(
                f"⚠️ {signal.get('symbol')}: "
                f"не удалось проверить сигнал: {error}"
            )
            continue

        if updates:
            results.append((index, signal, updates))

    if not results:
        return

    # 3) применяем к свежей версии файла
    closed = 0

    with _file_lock:
        signals = _read_signals()

        for index, original, updates in results:
            if index >= len(signals):
                continue

            current = signals[index]

            if (
                current.get("symbol") != original.get("symbol")
                or current.get("signal_time") != original.get("signal_time")
                or current.get("status") != "ACTIVE"
            ):
                continue

            current.update(updates)

            if updates.get("status") in ("TP", "SL"):
                closed += 1
                print(
                    f"🎯 {current['symbol']} — "
                    f"{updates['status']}"
                    + (" (SL и TP в одной свече, засчитан SL)"
                       if updates.get("ambiguous") else "")
                )

        _write_signals(signals)

    if closed:
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
