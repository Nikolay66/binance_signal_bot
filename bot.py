import asyncio
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config import TELEGRAM_TOKEN
from binance.client import get_price
from binance.market import (
    analyze_market,
    format_analysis,
    scan_market
)
from tracker import check_active_signals, get_statistics, get_active_signals

SCAN_RUNNING = False

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


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    statistics = get_statistics()

    text = (
        "📊 СТАТИСТИКА СИГНАЛОВ\n\n"

        f"📋 Всего сигналов: {statistics['total']}\n"
        f"✅ Take Profit: {statistics['tp']}\n"
        f"❌ Stop Loss: {statistics['sl']}\n"
        f"🔄 Активных: {statistics['active']}\n"
        f"🏁 Завершённых: {statistics['finished']}\n"
        f"🎯 Общий Win Rate: {statistics['win_rate']:.2f}%\n\n"
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
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\n\n"
        "/start — запуск бота\n"
        "/help — помощь"
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
            text += (
                f"{index}. 📌 {signal['symbol']}\n"
                f"   🎯 {signal['signal']}\n"
                f"   💵 Entry: {signal['entry_price']} USDT\n"
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

    if SCAN_RUNNING:
        print("⏳ AUTO SCAN — другое сканирование уже выполняется.")
        return

    SCAN_RUNNING = True
    check_active_signals()
    if CHAT_ID is None:
        print("AUTO SCAN: Chat ID ещё не получен. Нажмите /start.")
        SCAN_RUNNING = False
        return

    try:
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


def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("analyze", analyze))
    application.add_handler(CommandHandler("scan", scan))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("active", active))

    application.job_queue.run_repeating(
        auto_scan,
        interval=900,
        first=10
    )

    print("Бот запущен...")
    print("Автоматическое сканирование: каждые 15 минут")

    application.run_polling()


if __name__ == "__main__":
    main()
