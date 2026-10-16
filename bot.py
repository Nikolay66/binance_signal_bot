import asyncio
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime, timedelta
from config import TELEGRAM_TOKEN
from binance.client import get_price
from binance.market import (
    analyze_market,
    format_analysis,
    scan_market
)
from tracker import check_active_signals, get_statistics, get_active_signals

SCAN_RUNNING = False
LAST_SCAN_TIME = None
BOT_START_TIME = datetime.now()

try:
    with open("chat_id.txt", "r") as file:
        CHAT_ID = int(file.read().strip())
        print(f"CHAT_ID загружен: {CHAT_ID}")

except (FileNotFoundError, ValueError):
    CHAT_ID = None
    print("CHAT_ID пока не сохранён.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID

    CHAT_ID = update.effective_chat.id

    with open("chat_id.txt", "w") as file:
        file.write(str(CHAT_ID))

    print(f"DEBUG START: CHAT_ID = {CHAT_ID}")

    await update.message.reply_text(
        "Привет! 👋\n"
        "Я бот для анализа фьючерсных рынков Binance.\n\n"
        "Пока я нахожусь в разработке."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID
    global SCAN_RUNNING
    global LAST_SCAN_TIME

    if SCAN_RUNNING:
        scan_status = "🔄 Сканирование выполняется"
    else:
        scan_status = "🟢 Бот ожидает сканирование"

    if CHAT_ID is not None:
        chat_status = "🟢 Chat ID загружен"
    else:
        chat_status = "🔴 Chat ID не найден"

    if LAST_SCAN_TIME is not None:
        last_scan = LAST_SCAN_TIME.strftime("%d.%m.%Y %H:%M:%S")
    else:
        last_scan = "Ещё не было"

    if LAST_SCAN_TIME is not None:
        next_scan = LAST_SCAN_TIME + timedelta(minutes=15)
        next_scan_text = next_scan.strftime("%d.%m.%Y %H:%M:%S")
    else:
        next_scan_text = "Ещё не определено"

    uptime = datetime.now() - BOT_START_TIME

    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)

    uptime_text = f"{hours} ч {minutes} мин"

    active_signals = get_active_signals()
    active_count = len(active_signals)
    stats = get_statistics()

    active_long = stats["active_long"]
    active_short = stats["active_short"]

    tp_count = stats["tp"]
    sl_count = stats["sl"]

    long_tp = stats["long_tp"]
    long_sl = stats["long_sl"]
    long_win_rate = stats["long_win_rate"]

    short_tp = stats["short_tp"]
    short_sl = stats["short_sl"]
    short_win_rate = stats["short_win_rate"]

    current_streak = stats["current_streak"]
    current_streak_result = stats["current_streak_result"]

    text = (
        "🤖 СТАТУС БОТА\n\n"

        f"Состояние: {scan_status}\n"
        f"Chat ID: {chat_status}\n"
        f"Автосканирование: каждые 15 минут\n\n"

        f"🕐 Последнее сканирование: {last_scan}\n"
        f"⏭ Следующее сканирование: {next_scan_text}\n\n"
        f"⏱ Время работы: {uptime_text}\n\n"

        "📊 АКТИВНЫЕ СИГНАЛЫ\n"
        f"Всего: {active_count}\n"
        f"🟢 LONG: {active_long}\n"
        f"🔴 SHORT: {active_short}\n\n"

        "📈 СТАТИСТИКА\n"
        f"Всего сигналов: {stats['total']}\n"
        f"✅ Take Profit: {tp_count}\n"
        f"❌ Stop Loss: {sl_count}\n"
        f"Win Rate: {stats['win_rate']:.2f}%\n"
        f"Результат: {stats['total_r']:+.2f}R\n"
        f"Profit Factor: {stats['profit_factor']:.2f}\n"

        "\n"
        "🟢 LONG\n"
        f"TP: {long_tp}\n"
        f"SL: {long_sl}\n"
        f"Win Rate: {long_win_rate:.2f}%\n\n"

        "🔴 SHORT\n"
        f"TP: {short_tp}\n"
        f"SL: {short_sl}\n"
        f"Win Rate: {short_win_rate:.2f}%\n"

        "\n"
        "🔥 ТЕКУЩАЯ СЕРИЯ\n"
        f"Результат: {current_streak_result}\n"
        f"Серия: {current_streak}\n"
    )

    await update.message.reply_text(text)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    statistics = get_statistics()
    reliability = statistics["reliability"]

    text = (
        "📊 СТАТИСТИКА СИГНАЛОВ\n\n"

        f"📋 Всего сигналов: {statistics['total']}\n"
        f"✅ Take Profit: {statistics['tp']}\n"
        f"❌ Stop Loss: {statistics['sl']}\n"
        f"🔄 Активных: {statistics['active']}\n"
        f"🏁 Завершённых: {statistics['finished']}\n"
        f"🎯 Общий Win Rate: {statistics['win_rate']:.2f}%\n\n"
        f"📊 Надёжность статистики: {reliability}\n"
        f"💰 Результат: {statistics['total_r']:+.2f}R\n\n"
        f"📊 Profit Factor: {statistics['profit_factor']:.2f}\n"
        f"⏱ Среднее время сделки: "
        f"{statistics['average_duration'] / 3600:.1f} ч\n"
        f"🔥 Текущая серия: "
        f"{statistics['current_streak']} "
        f"{statistics['current_streak_result'] or '-'} подряд\n"
        f"📉 Max Drawdown: -{statistics['max_drawdown_r']:.2f}R\n\n"
        f"📈 Средний R на TP: +{statistics['average_tp_r']:.2f}R\n"
        f"📊 Средний R на сделку: {statistics['average_r_per_trade']:+.2f}R\n\n"
        "🟢 LONG\n"
        f"✅ TP: {statistics['long_tp']}\n"
        f"❌ SL: {statistics['long_sl']}\n"
        f"🔄 Active: {statistics['active_long']}\n"
        f"🎯 Win Rate: {statistics['long_win_rate']:.2f}%\n"
        f"💰 Result: {statistics['long_r']:+.2f}R\n\n"

        "🔴 SHORT\n"
        f"✅ TP: {statistics['short_tp']}\n"
        f"❌ SL: {statistics['short_sl']}\n"
        f"🔄 Active: {statistics['active_short']}\n"
        f"🎯 Win Rate: {statistics['short_win_rate']:.2f}%\n"
        f"💰 Result: {statistics['short_r']:+.2f}R"
    )

    score_statistics = statistics["score_statistics"]

    if score_statistics:
        text += "\n📊 СТАТИСТИКА ПО SCORE\n\n"

        for score in sorted(score_statistics):
            data = score_statistics[score]

            text += (
                f"Score {score}:\n"
                f"  ✅ TP: {data['tp']}\n"
                f"  ❌ SL: {data['sl']}\n"
                f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
                f"  💰 Result: {data['r']:+.2f}R\n\n"
            )
    score_direction_statistics = statistics[
        "score_direction_statistics"
    ]

    if score_direction_statistics:
        text += "📊 SCORE + НАПРАВЛЕНИЕ\n\n"

        for score in sorted(score_direction_statistics):
            text += f"Score {score}:\n"

            for direction in ["LONG", "SHORT"]:
                data = score_direction_statistics[score][direction]

                finished_direction = data["tp"] + data["sl"]

                if finished_direction == 0:
                    continue

                text += (
                    f"  {'🟢' if direction == 'LONG' else '🔴'} "
                    f"{direction}: "
                    f"TP {data['tp']} / "
                    f"SL {data['sl']} | "
                    f"Win {data['win_rate']:.2f}% | "
                    f"R {data['r']:+.2f}\n"
                )

            text += "\n"
    confidence_statistics = statistics[
        "confidence_statistics"
    ]

    text += "🎯 СТАТИСТИКА ПО CONFIDENCE\n\n"

    for group in ["70-79", "80-89", "90-100"]:
        data = confidence_statistics[group]

        finished_confidence = data["tp"] + data["sl"]

        if finished_confidence == 0:
            continue

        text += (
            f"{group}%:\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )
    trend_1h_statistics = statistics["trend_1h_statistics"]

    text += "📊 SIGNAL + 1H TREND\n\n"

    for group in ["LONG_UP", "LONG_DOWN", "SHORT_UP", "SHORT_DOWN"]:
        data = trend_1h_statistics[group]

        finished_trend = data["tp"] + data["sl"]

        if finished_trend == 0:
            continue

        direction, trend_1h = group.split("_")

        direction_emoji = "🟢" if direction == "LONG" else "🔴"
        trend_emoji = "🟢" if trend_1h == "UP" else "🔴"

        text += (
            f"{direction_emoji} {direction} + "
            f"{trend_emoji} 1H {trend_1h}:\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    btc_trend_text = statistics.get("btc_trend_text", "")

    if btc_trend_text:
        text += btc_trend_text + "\n"

    coin_trend_text = statistics.get("coin_trend_text", "")

    if coin_trend_text:
        text += coin_trend_text + "\n"
    score_direction_text = statistics.get("score_direction_text", "")

    if score_direction_text:
        text += score_direction_text + "\n"
        score_trend_text = statistics.get("score_trend_text", "")

    if score_trend_text:
        text += score_trend_text + "\n"

    score_coin_btc_text = statistics.get("score_coin_btc_text", "")

    if score_coin_btc_text:
        text += score_coin_btc_text + "\n"

    duration_statistics = statistics["duration_statistics"]

    text += "⏱ СТАТИСТИКА ПО ДЛИТЕЛЬНОСТИ\n\n"

    duration_names = {
        "0-1h": "До 1 часа",
        "1-3h": "1–3 часа",
        "3-6h": "3–6 часов",
        "6-12h": "6–12 часов",
        "12h+": "Более 12 часов"
    }

    for group in ["0-1h", "1-3h", "3-6h", "6-12h", "12h+"]:
        data = duration_statistics[group]

        finished_duration = data["tp"] + data["sl"]

        if finished_duration == 0:
            continue

        text += (
            f"{duration_names[group]}:\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    score_duration_statistics = statistics[
        "score_duration_statistics"
    ]

    text += "📊 SCORE + ДЛИТЕЛЬНОСТЬ\n\n"

    duration_names = {
        "0-1h": "До 1 часа",
        "1-3h": "1–3 часа",
        "3-6h": "3–6 часов",
        "6-12h": "6–12 часов",
        "12h+": "Более 12 часов"
    }

    for score in sorted(score_duration_statistics):

        text += f"Score {score}:\n"

        for duration_group in [
            "0-1h",
            "1-3h",
            "3-6h",
            "6-12h",
            "12h+"
        ]:

            if duration_group not in score_duration_statistics[score]:
                continue

            data = score_duration_statistics[score][duration_group]

            finished_score_duration = (
                data["tp"] + data["sl"]
            )

            if finished_score_duration == 0:
                continue

            text += (
                f"  {duration_names[duration_group]}: "
                f"TP {data['tp']} / "
                f"SL {data['sl']} | "
                f"Win {data['win_rate']:.2f}% | "
                f"R {data['r']:+.2f}\n"
            )

        text += "\n"

    score_direction_duration_statistics = statistics[
        "score_direction_duration_statistics"
    ]

    text += "📊 SCORE + НАПРАВЛЕНИЕ + ДЛИТЕЛЬНОСТЬ\n\n"

    duration_names = {
        "0-1h": "До 1 часа",
        "1-3h": "1–3 часа",
        "3-6h": "3–6 часов",
        "6-12h": "6–12 часов",
        "12h+": "Более 12 часов"
    }

    for score in sorted(score_direction_duration_statistics):

        text += f"Score {score}:\n"

        for direction in ["LONG", "SHORT"]:

            durations = score_direction_duration_statistics[
                score
            ][direction]

            for duration_group in [
                "0-1h",
                "1-3h",
                "3-6h",
                "6-12h",
                "12h+"
            ]:

                if duration_group not in durations:
                    continue

                data = durations[duration_group]

                finished = data["tp"] + data["sl"]

                if finished == 0:
                    continue

                direction_emoji = (
                    "🟢"
                    if direction == "LONG"
                    else "🔴"
                )

                text += (
                    f"  {direction_emoji} {direction} + "
                    f"{duration_names[duration_group]}: "
                    f"TP {data['tp']} / "
                    f"SL {data['sl']} | "
                    f"Win {data['win_rate']:.2f}% | "
                    f"R {data['r']:+.2f}\n"
                )

        text += "\n"

    volume_statistics = statistics["volume_statistics"]

    volume_strength_statistics = (
        statistics["volume_strength_statistics"]
    )

    score_2_long_up_bullish_volume_statistics = (
        statistics["score_2_long_up_bullish_volume_statistics"]
    )

    score_2_bullish_direction_statistics = (
        statistics["score_2_bullish_direction_statistics"]
    )
    score_2_bullish_long_confidence_statistics = (
        statistics["score_2_bullish_long_confidence_statistics"]
    )

    score_2_bullish_long_reasons_statistics = (
        statistics["score_2_bullish_long_reasons_statistics"]
    )

    text += "📊 VOLUME + RESULT\n\n"

    volume_names = {
        "bullish": "🟢 Bullish",
        "bearish": "🔴 Bearish",
        "neutral": "⚪ Neutral"
    }

    for volume_direction in [
        "bullish",
        "bearish",
        "neutral"
    ]:

        if volume_direction not in volume_statistics:
            continue

        data = volume_statistics[volume_direction]

        finished_volume = data["tp"] + data["sl"]

        if finished_volume == 0:
            continue

        text += (
            f"{volume_names[volume_direction]}:\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    text += (
        "📊 СИЛА ОБЪЁМА — RESULT\n\n"
    )

    for volume_strength, data in volume_strength_statistics.items():

        finished = data["tp"] + data["sl"]

        if finished == 0:
            continue

        text += (
            f"🔹 Volume {volume_strength}:\n"
            f"  Сделок: {finished}\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    text += (
        "📊 SCORE 2 + LONG + UP + BULLISH — СИЛА ОБЪЁМА\n\n"
    )

    for volume_strength, data in score_2_long_up_bullish_volume_statistics.items():

        finished = data["tp"] + data["sl"]

        if finished == 0:
            continue

        text += (
            f"🔹 Volume {volume_strength}:\n"
            f"  Сделок: {finished}\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    text += (
        "📊 SCORE 2 + BULLISH — НАПРАВЛЕНИЕ\n\n"
    )

    for direction, data in score_2_bullish_direction_statistics.items():

        finished = data["tp"] + data["sl"]

        if finished == 0:
            continue

        text += (
            f"🔹 {direction}:\n"
            f"  Сделок: {finished}\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    text += (
        "📊 SCORE 2 + BULLISH + LONG — CONFIDENCE\n\n"
    )

    for confidence_range, data in score_2_bullish_long_confidence_statistics.items():

        finished = data["tp"] + data["sl"]

        if finished == 0:
            continue

        text += (
            f"🔹 Confidence {confidence_range}%:\n"
            f"  Сделок: {finished}\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    text += (
        "📊 SCORE 2 + BULLISH + LONG — ПРИЧИНЫ\n\n"
    )

    for reasons_key, data in score_2_bullish_long_reasons_statistics.items():

        finished = data["tp"] + data["sl"]

        if finished == 0:
            continue

        text += (
            f"🔹 {reasons_key}:\n"
            f"  Сделок: {finished}\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    score_volume_statistics = statistics["score_volume_statistics"]

    text += "📊 SCORE + VOLUME\n\n"

    volume_names = {
        "bullish": "🟢 Bullish",
        "bearish": "🔴 Bearish",
        "neutral": "⚪ Neutral"
    }

    for (score, volume_direction), data in sorted(
        score_volume_statistics.items()
    ):

        finished_score_volume = data["tp"] + data["sl"]

        if finished_score_volume == 0:
            continue

        text += (
            f"Score {score} + "
            f"{volume_names[volume_direction]}:\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    score_volume_direction_statistics = (
        statistics["score_volume_direction_statistics"]
    )

    score_volume_direction_trend_statistics = (
        statistics["score_volume_direction_trend_statistics"]
    )

    score_volume_direction_trend_confidence_statistics = (
        statistics[
            "score_volume_direction_trend_confidence_statistics"
        ]
    )

    combination_quality_statistics = (
        statistics["combination_quality_statistics"]
    )

    recent_statistics = statistics["recent_statistics"]
    monthly_statistics = statistics["monthly_statistics"]
    recent_comparison = statistics["recent_comparison"]

    recent_direction_statistics = (
        statistics["recent_direction_statistics"]
    )

    recent_trend_statistics = (
        statistics["recent_trend_statistics"]
    )

    recent_score_trend_statistics = (
        statistics["recent_score_trend_statistics"]
    )

    recent_score_trend_volume_statistics = (
        statistics["recent_score_trend_volume_statistics"]
    )

    recent_problem_symbol_statistics = (
        statistics["recent_problem_symbol_statistics"]
    )

    text += "📊 SCORE + VOLUME + DIRECTION\n\n"

    direction_names = {
        "LONG": "🟢 LONG",
        "SHORT": "🔴 SHORT"
    }

    for (
        score,
        volume_direction,
        direction
    ), data in sorted(
        score_volume_direction_statistics.items()
    ):

        finished_combination = data["tp"] + data["sl"]

        if finished_combination == 0:
            continue

        text += (
            f"Score {score} + "
            f"{volume_names[volume_direction]} + "
            f"{direction_names[direction]}:\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    text += "📊 SCORE + VOLUME + DIRECTION + TREND\n\n"

    trend_names = {
        "UP": "📈 UP",
        "DOWN": "📉 DOWN"
    }

    for (
        score,
        volume_direction,
        direction,
        trend_1h
    ), data in sorted(
        score_volume_direction_trend_statistics.items()
    ):

        finished_combination = data["tp"] + data["sl"]

        if finished_combination == 0:
            continue

        text += (
            f"Score {score} + "
            f"{volume_names[volume_direction]} + "
            f"{direction_names[direction]} + "
            f"{trend_names[trend_1h]}:\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    text += "📊 SCORE + VOLUME + DIRECTION + TREND + CONFIDENCE\n\n"

    confidence_names = {
        "70-79": "🟡 70-79%",
        "80-89": "🟠 80-89%",
        "90-100": "🟢 90-100%"
    }

    for (
        score,
        volume_direction,
        direction,
        trend_1h,
        confidence_group
    ), data in sorted(
        score_volume_direction_trend_confidence_statistics.items()
    ):

        finished_combination = data["tp"] + data["sl"]

        if finished_combination == 0:
            continue

        text += (
            f"Score {score} + "
            f"{volume_names[volume_direction]} + "
            f"{direction_names[direction]} + "
            f"{trend_names[trend_1h]} + "
            f"{confidence_names[confidence_group]}:\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    text += "📊 КАЧЕСТВО КОМБИНАЦИЙ\n\n"

    if combination_quality_statistics:

        text += "🟢 ЛУЧШИЕ КОМБИНАЦИИ\n\n"

        for item in combination_quality_statistics[:5]:

            text += (
                f"Score {item['score']} + "
                f"{volume_names[item['volume_direction']]} + "
                f"{direction_names[item['direction']]} + "
                f"{trend_names[item['trend_1h']]} + "
                f"{confidence_names[item['confidence']]}:\n"
                f"  Сделок: {item['finished']}\n"
                f"  TP: {item['tp']} / SL: {item['sl']}\n"
                f"  Win Rate: {item['win_rate']:.2f}%\n"
                f"  Result: {item['r']:+.2f}R\n\n"
            )

        text += "🔴 ХУДШИЕ КОМБИНАЦИИ\n\n"

        for item in reversed(combination_quality_statistics[-5:]):

            text += (
                f"Score {item['score']} + "
                f"{volume_names[item['volume_direction']]} + "
                f"{direction_names[item['direction']]} + "
                f"{trend_names[item['trend_1h']]} + "
                f"{confidence_names[item['confidence']]}:\n"
                f"  Сделок: {item['finished']}\n"
                f"  TP: {item['tp']} / SL: {item['sl']}\n"
                f"  Win Rate: {item['win_rate']:.2f}%\n"
                f"  Result: {item['r']:+.2f}R\n\n"
            )

    text += "📊 ПОСЛЕДНИЕ СИГНАЛЫ\n\n"

    for period in [20, 50]:

        data = recent_statistics.get(period)

        if not data:
            continue

        text += (
            f"📌 Последние {period} завершённых:\n"
            f"  ✅ TP: {data['tp']}\n"
            f"  ❌ SL: {data['sl']}\n"
            f"  🏁 Всего: {data['finished']}\n"
            f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
            f"  💰 Result: {data['r']:+.2f}R\n\n"
        )

    data_20 = recent_statistics.get(20)
    data_50 = recent_statistics.get(50)

    if data_20 and data_50:
        text += "📈 СРАВНЕНИЕ РЕЗУЛЬТАТОВ\n\n"

        win_rate_diff = data_20["win_rate"] - data_50["win_rate"]
        result_diff = data_20["r"] - data_50["r"]

        if win_rate_diff > 2 and result_diff > 0:
            trend = "📈 Результаты улучшаются"
        elif win_rate_diff < -2 and result_diff < 0:
            trend = "📉 Результаты ухудшаются"
        else:
            trend = "➡️ Нет однозначного изменения"

        text += (
            f"Win Rate за 20 сигналов: {data_20['win_rate']:.2f}%\n"
            f"Win Rate за 50 сигналов: {data_50['win_rate']:.2f}%\n"
            f"Разница Win Rate: {win_rate_diff:+.2f}%\n\n"
            f"Результат за 20 сигналов: {data_20['r']:+.2f}R\n"
            f"Результат за 50 сигналов: {data_50['r']:+.2f}R\n"
            f"Разница результатов: {result_diff:+.2f}R\n\n"
            f"Оценка: {trend}\n\n"
        )

    # Сравнение двух последовательных периодов по 20 сигналов
    last_20 = recent_comparison["last_20"]
    previous_20 = recent_comparison["previous_20"]

    if previous_20["finished"] > 0 and last_20["finished"] > 0:
        win_rate_change = last_20["win_rate"] - previous_20["win_rate"]
        result_change = last_20["r"] - previous_20["r"]

        if win_rate_change > 2 and result_change > 0:
            comparison_trend = "📈 Результаты улучшаются"
        elif win_rate_change < -2 and result_change < 0:
            comparison_trend = "📉 Результаты ухудшаются"
        else:
            comparison_trend = "➡️ Нет однозначного изменения"

        text += (
            "📊 СРАВНЕНИЕ ДВУХ ПЕРИОДОВ\n\n"
            "Последние 20 сигналов:\n"
            f"  ✅ TP: {last_20['tp']} | ❌ SL: {last_20['sl']}\n"
            f"  🎯 Win Rate: {last_20['win_rate']:.2f}%\n"
            f"  💰 Result: {last_20['r']:+.2f}R\n\n"
            "Предыдущие 20 сигналов:\n"
            f"  ✅ TP: {previous_20['tp']} | ❌ SL: {previous_20['sl']}\n"
            f"  🎯 Win Rate: {previous_20['win_rate']:.2f}%\n"
            f"  💰 Result: {previous_20['r']:+.2f}R\n\n"
            f"Изменение Win Rate: {win_rate_change:+.2f}%\n"
            f"Изменение результата: {result_change:+.2f}R\n\n"
            f"Оценка: {comparison_trend}\n\n"
        )
    else:
        text += (
            "📊 СРАВНЕНИЕ ДВУХ ПЕРИОДОВ\n\n"
            "Недостаточно завершённых сигналов "
            "для сравнения двух периодов.\n\n"
        )

    text += "📊 ПОСЛЕДНИЕ СИГНАЛЫ — LONG / SHORT\n\n"

    for period in [20, 50]:

        direction_stats = recent_direction_statistics.get(period)

        if not direction_stats:
            continue

        text += f"📌 Последние {period} завершённых:\n\n"

        for direction in ["LONG", "SHORT"]:

            data = direction_stats.get(direction)

            if not data:
                continue

            text += (
                f"{direction_names[direction]}:\n"
                f"  ✅ TP: {data['tp']}\n"
                f"  ❌ SL: {data['sl']}\n"
                f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
                f"  💰 Result: {data['r']:+.2f}R\n\n"
            )

    text += "📊 ПОСЛЕДНИЕ СИГНАЛЫ — SIGNAL + 1H TREND\n\n"

    for period in [20, 50]:

        trend_stats = recent_trend_statistics.get(period)

        if not trend_stats:
            continue

        text += f"📌 Последние {period} завершённых:\n\n"

        for direction, trend_1h in [
            ("LONG", "UP"),
            ("LONG", "DOWN"),
            ("SHORT", "UP"),
            ("SHORT", "DOWN")
        ]:

            data = trend_stats.get(
                (direction, trend_1h)
            )

            if not data:
                continue

            text += (
                f"{direction_names[direction]} + "
                f"{trend_names[trend_1h]}:\n"
                f"  ✅ TP: {data['tp']}\n"
                f"  ❌ SL: {data['sl']}\n"
                f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
                f"  💰 Result: {data['r']:+.2f}R\n\n"
            )

    text += "📊 ПОСЛЕДНИЕ СИГНАЛЫ — SCORE + SIGNAL + 1H TREND\n\n"

    for period in [20, 50]:

        score_trend_stats = recent_score_trend_statistics.get(
            period
        )

        if not score_trend_stats:
            continue

        text += f"📌 Последние {period} завершённых:\n\n"

        for (
            score,
            direction,
            trend_1h
        ), data in sorted(
            score_trend_stats.items()
        ):

            finished = data["tp"] + data["sl"]

            if finished == 0:
                continue

            text += (
                f"Score {score} + "
                f"{direction_names[direction]} + "
                f"{trend_names[trend_1h]}:\n"
                f"  Сделок: {finished}\n"
                f"  ✅ TP: {data['tp']}\n"
                f"  ❌ SL: {data['sl']}\n"
                f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
                f"  💰 Result: {data['r']:+.2f}R\n\n"
            )

    text += (
        "📊 ПОСЛЕДНИЕ СИГНАЛЫ — "
        "SCORE + SIGNAL + 1H TREND + VOLUME\n\n"
    )

    for period in [20, 50]:

        score_trend_volume_stats = (
            recent_score_trend_volume_statistics.get(period)
        )

        if not score_trend_volume_stats:
            continue

        text += f"📌 Последние {period} завершённых:\n\n"

        for (
            score,
            direction,
            trend_1h,
            volume_direction
        ), data in sorted(score_trend_volume_stats.items()):

            finished = data["tp"] + data["sl"]

            if finished == 0:
                continue

            text += (
                f"Score {score} + "
                f"{direction_names[direction]} + "
                f"{trend_names[trend_1h]} + "
                f"{volume_names[volume_direction]}:\n"
                f"  Сделок: {finished}\n"
                f"  ✅ TP: {data['tp']}\n"
                f"  ❌ SL: {data['sl']}\n"
                f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
                f"  💰 Result: {data['r']:+.2f}R\n\n"
            )

    text += (
        "📊 ПРОБЛЕМНАЯ КОМБИНАЦИЯ — ПО МОНЕТАМ\n\n"
    )

    for period in [20, 50]:

        symbol_stats = (
            recent_problem_symbol_statistics.get(period)
        )

        if not symbol_stats:
            continue

        text += (
            f"📌 Score 2 + LONG + UP + "
            f"Bullish — последние {period}:\n\n"
        )

        for symbol, data in sorted(
            symbol_stats.items(),
            key=lambda item: item[1]["r"]
        ):

            finished = data["tp"] + data["sl"]

            if finished == 0:
                continue

            text += (
                f"🔹 {symbol}:\n"
                f"  Сделок: {finished}\n"
                f"  ✅ TP: {data['tp']}\n"
                f"  ❌ SL: {data['sl']}\n"
                f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
                f"  💰 Result: {data['r']:+.2f}R\n\n"
            )

    score_confidence_statistics = statistics[
        "score_confidence_statistics"
    ]

    text += "📊 SCORE + CONFIDENCE\n\n"

    for score in sorted(score_confidence_statistics):

        text += f"Score {score}:\n"

        for confidence_group in [
            "70-79",
            "80-89",
            "90-100"
        ]:

            if (
                confidence_group
                not in score_confidence_statistics[score]
            ):
                continue

            data = score_confidence_statistics[
                score
            ][confidence_group]

            finished = data["tp"] + data["sl"]

            if finished == 0:
                continue

            text += (
                f"  {confidence_group}%: "
                f"TP {data['tp']} / "
                f"SL {data['sl']} | "
                f"Win {data['win_rate']:.2f}% | "
                f"R {data['r']:+.2f}\n"
            )

        text += "\n"

    # Статистика по месяцам
    if monthly_statistics:
        months = sorted(monthly_statistics.keys())
        last_month = months[-1]
        previous_month = months[-2] if len(months) >= 2 else None

        text += "📅 СТАТИСТИКА ПО МЕСЯЦАМ\n\n"

        for month in [previous_month, last_month]:
            if month is None:
                continue

            data = monthly_statistics[month]

            text += (
                f"📌 {month}\n"
                f"  ✅ TP: {data['tp']}\n"
                f"  ❌ SL: {data['sl']}\n"
                f"  🏁 Всего: {data['finished']}\n"
                f"  🎯 Win Rate: {data['win_rate']:.2f}%\n"
                f"  💰 Result: {data['r']:+.2f}R\n\n"
            )

        if previous_month is not None:
            current = monthly_statistics[last_month]
            previous = monthly_statistics[previous_month]

            win_rate_change = (
                current["win_rate"] - previous["win_rate"]
            )
            result_change = current["r"] - previous["r"]

            text += (
                "📊 СРАВНЕНИЕ МЕСЯЦЕВ\n\n"
                f"Изменение Win Rate: {win_rate_change:+.2f}%\n"
                f"Изменение результата: {result_change:+.2f}R\n\n"
            )

    max_length = 4000

    for i in range(0, len(text), max_length):
        await update.message.reply_text(
            text[i:i + max_length]
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(

        "🤖 КОМАНДЫ БОТА\n\n"

        "/start — запуск бота\n"
        "/help — список команд\n"
        "/price BTCUSDT — текущая цена\n"
        "/status — состояние и статистика\n"
        "/active — активные сигналы\n"
        "/stats — полная статистика"

    )


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Укажите торговую пару.\n\n"
            "Пример:\n"
            "/price BTCUSDT"
        )
        return

    symbol = context.args[0].upper()

    try:
        current_price = get_price(symbol)

        await update.message.reply_text(
            f"💰 {symbol}\n"
            f"Цена: {current_price} USDT"
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось получить цену.\n"
            "Проверьте название торговой пары."
        )


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Укажите торговую пару.\n\n"
            "Пример:\n"
            "/analyze BTCUSDT"
        )
        return

    symbol = context.args[0].upper()

    try:
        result = analyze_market(symbol, "15m", 15)
        current_price = get_price(symbol)

        text = format_analysis(result)

        text = (
            f"💰 Текущая цена: {current_price} USDT\n\n"
            + text
        )

        await update.message.reply_text(text)

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось выполнить анализ.\n"
            "Проверьте название торговой пары."
        )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open("signals.json", "r", encoding="utf-8") as file:
            signals = json.load(file)

        finished_signals = [
            signal for signal in signals
            if signal.get("status") in ["TP", "SL"]
        ]

        finished_signals.sort(
            key=lambda x: x.get("result_time", ""),
            reverse=True
        )

        finished_signals = finished_signals[:10]

        if not finished_signals:
            await update.message.reply_text(
                "📜 История сигналов пока пуста."
            )
            return

        text = "📜 ИСТОРИЯ СИГНАЛОВ\n\n"

        for index, signal in enumerate(finished_signals, start=1):

            if signal["result"] == "TP":
                result_emoji = "✅"
                result_r = signal["risk_reward"]
            else:
                result_emoji = "❌"
                result_r = -1

            text += (
                f"{index}. {signal['symbol']} — "
                f"{signal['signal']} "
                f"{result_emoji} {signal['result']}\n"
                f"   R: {result_r:+.2f}\n"
                f"   Время: {signal.get('result_time', '-')}\n\n"
            )

        await update.message.reply_text(text)

    except Exception as error:
        print(f"❌ HISTORY ERROR: {error}")
        await update.message.reply_text(
            "❌ Не удалось получить историю сигналов."
        )


async def active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        signals = get_active_signals()

        if not signals:
            await update.message.reply_text(
                "🔄 Активных сигналов сейчас нет."
            )
            return

        text = "🔄 АКТИВНЫЕ СИГНАЛЫ\n\n"

        for index, signal in enumerate(signals, start=1):
            current_price = get_price(signal["symbol"])

            entry_price = signal["entry_price"]

            if signal["signal"] == "LONG":
                pnl_percent = ((current_price - entry_price) /
                               entry_price) * 100
            else:
                pnl_percent = ((entry_price - current_price) /
                               entry_price) * 100
            if pnl_percent >= 0:
                pnl_emoji = "🟢"
            else:
                pnl_emoji = "🔴"

            text += (
                f"{index}. 📌 {signal['symbol']}\n"
                f"   🎯 {signal['signal']}\n"
                f"   💵 Entry: {signal['entry_price']} USDT\n"
                f"   📍 Current: {current_price} USDT\n"
                f"   {pnl_emoji} P/L: {pnl_percent:+.2f}%\n"
                f"   🛑 SL: {signal['stop_loss']} USDT\n"
                f"   🎯 TP: {signal['take_profit']} USDT\n"
                f"   📊 Score: {signal['score']}\n"
                f"   ⚖️ R:R: 1 : {signal['risk_reward']}\n"
                f"   🕐 Время: {signal['signal_time']}\n\n"
            )

        await update.message.reply_text(text)

    except Exception as error:
        print(f"❌ ACTIVE ERROR: {error}")
        await update.message.reply_text(
            "❌ Не удалось получить активные сигналы."
        )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SCAN_RUNNING

    if SCAN_RUNNING:
        await update.message.reply_text(
            "⏳ Сканирование уже выполняется.\n"
            "Дождитесь его завершения."
        )
        return

    SCAN_RUNNING = True

    try:
        await update.message.reply_text(
            "🔎 Начинаю сканирование рынка...\n"
            "Это может занять некоторое время."
        )

        scan_result = scan_market()

        signals = scan_result["signals"]
        no_trade_results = scan_result["no_trade"]
        rejected_results = scan_result["rejected"]

        if not signals:
            text = (
                "🔎 Сканирование завершено.\n\n"
                "🟢 Новых торговых сигналов: 0"
            )

            await update.message.reply_text(text)
            return

        text = "🔎 СИГНАЛЫ РЫНКА\n\n"

        for signal in signals:
            text += (
                f"📌 {signal['symbol']}\n"
                f"🎯 Сигнал: {signal['signal']}\n"
                f"📊 Score: {signal['score']}\n"
                f"📈 Trend: {signal['trend']}\n"
                f"📉 RSI: {signal['rsi']}\n"
                f"📊 Volume Balance: {signal['volume_balance']}x\n\n"
                f"💵 Entry: {signal['entry_price']} USDT\n"
                f"🛑 Stop Loss: {signal['stop_loss']} USDT "
                f"({signal['risk_percent']}%)\n"
                f"🎯 Take Profit: {signal['take_profit']} USDT "
                f"({signal['reward_percent']}%)\n"
                f"⚖️ Risk/Reward: 1 : {signal['risk_reward']}\n\n"
                f"🎯 Confidence: {signal['confidence']}%\n"
                f"⚠️ Risk: {signal['risk']}\n\n"
                f"💡 Причина:\n{signal['signal_reason']}\n\n"
            )

        await update.message.reply_text(text)

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось выполнить сканирование рынка."
        )
    finally:
        SCAN_RUNNING = False


async def auto_scan(context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID
    global SCAN_RUNNING
    global LAST_SCAN_TIME

    if SCAN_RUNNING:
        print("⏳ AUTO SCAN — другое сканирование уже выполняется.")
        return

    SCAN_RUNNING = True
    LAST_SCAN_TIME = datetime.now()

    try:
        if CHAT_ID is None:
            print("AUTO SCAN: Chat ID ещё не получен. Нажмите /start.")
            return

        print("\n🔄 AUTO SCAN — начинаю автоматическое сканирование...")

        scan_result = await asyncio.to_thread(scan_market)

        signals = scan_result["signals"]

        if not signals:
            print("AUTO SCAN — сигналов нет.")
            return

        text = "🔎 АВТОМАТИЧЕСКИЕ СИГНАЛЫ\n\n"

        for signal in signals:
            text += (
                f"📌 {signal['symbol']}\n"
                f"🎯 Сигнал: {signal['signal']}\n"
                f"🕐 Время сигнала: {signal['signal_time']}\n"
                f"📊 Score: {signal['score']}\n"
                f"📈 Trend: {signal['trend']}\n"
                f"📉 RSI: {signal['rsi']}\n"
                f"📊 Volume Balance: "
                f"{signal['volume_balance']}x\n\n"
                f"💵 Entry: {signal['entry_price']} USDT\n"
                f"🛑 Stop Loss: {signal['stop_loss']} USDT "
                f"({signal['risk_percent']}%)\n"
                f"🎯 Take Profit: {signal['take_profit']} USDT "
                f"({signal['reward_percent']}%)\n"
                f"⚖️ Risk/Reward: 1 : {signal['risk_reward']}\n\n"
                f"🎯 Confidence: {signal['confidence']}%\n"
                f"⚠️ Risk: {signal['risk']}\n\n"
                f"💡 Причина:\n"
                f"{signal['signal_reason']}\n\n"
            )

        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=text
        )

        print("AUTO SCAN — сигналы отправлены в Telegram.")

    except Exception as error:
        print(f"❌ AUTO SCAN ERROR: {error}")
    finally:
        SCAN_RUNNING = False


async def check_signals_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        print("🔎 Проверка активных сигналов...")
        await asyncio.to_thread(check_active_signals)
        print("✅ Проверка активных сигналов завершена.")
    except Exception as error:
        print(f"❌ CHECK SIGNALS ERROR: {error}")


def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("analyze", analyze))
    application.add_handler(CommandHandler("scan", scan))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("active", active))

    application.job_queue.run_repeating(
        auto_scan,
        interval=900,
        first=10
    )

    application.job_queue.run_repeating(
        check_signals_job,
        interval=60,
        first=15
    )

    print("Бот запущен...")
    print("Автоматическое сканирование: каждые 15 минут")

    application.run_polling()


if __name__ == "__main__":
    main()
