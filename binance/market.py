import httpx
from tracker import save_signal, has_active_signal
from datetime import datetime
from binance.client import get_1h_trend


def get_futures_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

    response = httpx.get(url)
    response.raise_for_status()

    data = response.json()

    symbols = []

    for item in data["symbols"]:
        if (
            item["quoteAsset"] == "USDT"
            and item["status"] == "TRADING"
        ):
            symbols.append(item["symbol"])

    return symbols


def get_top_volume_symbols(limit=30):
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"

    response = httpx.get(url)
    response.raise_for_status()

    data = response.json()

    symbols = get_futures_symbols()
    symbols_set = set(symbols)

    volume_data = []

    for item in data:
        symbol = item["symbol"]

        if symbol not in symbols_set:
            continue

        quote_volume = float(item["quoteVolume"])

        volume_data.append({
            "symbol": symbol,
            "quote_volume": quote_volume
        })

    volume_data.sort(
        key=lambda x: x["quote_volume"],
        reverse=True
    )

    return [
        item["symbol"]
        for item in volume_data[:limit]
    ]


def get_klines(symbol, interval="15m", limit=10):
    url = "https://fapi.binance.com/fapi/v1/klines"

    response = httpx.get(
        url,
        params={
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
    )

    response.raise_for_status()

    return response.json()


def format_candle(candle):
    return {
        "open": float(candle[1]),
        "high": float(candle[2]),
        "low": float(candle[3]),
        "close": float(candle[4]),
        "volume": float(candle[5])
    }


def candle_direction(candle):
    if candle["close"] > candle["open"]:
        return "БЫЧЬЯ"

    elif candle["close"] < candle["open"]:
        return "МЕДВЕЖЬЯ"

    else:
        return "НЕЙТРАЛЬНАЯ"


def get_trend(candles):
    first_candle = format_candle(candles[0])
    last_candle = format_candle(candles[-1])

    price_change = last_candle["close"] - first_candle["open"]

    if price_change > 0:
        return "ВОСХОДЯЩИЙ"

    elif price_change < 0:
        return "НИСХОДЯЩИЙ"

    else:
        return "БОКОВОЙ"


def analyze_market(symbol="BTCUSDT", interval="15m", limit=15):
    candles = get_klines(symbol, interval, limit)

    trend = get_trend(candles)

    resistance = max(float(candle[2]) for candle in candles)
    support = min(float(candle[3]) for candle in candles)
    current_price = float(candles[-1][4])

    # Дополнительные уровни за последние 5 свечей
    recent_candles = candles[-5:]

    recent_resistance = max(
        float(candle[2])
        for candle in recent_candles
    )

    recent_support = min(
        float(candle[3])
        for candle in recent_candles
    )
    recent_resistance_distance = (
        (recent_resistance - current_price) / current_price
    ) * 100

    recent_support_distance = (
        (current_price - recent_support) / current_price
    ) * 100
    print(
        f"DEBUG LEVELS {symbol} | "
        f"15 свечей: Support={support}, "
        f"Resistance={resistance} | "
        f"5 свечей: Support={recent_support}, "
        f"Resistance={recent_resistance} | "
        f"До 5-свечного сопротивления: "
        f"{recent_resistance_distance:.2f}% | "
        f"До 5-свечной поддержки: "
        f"{recent_support_distance:.2f}%"
    )

    resistance_distance = (
        (resistance - current_price) / current_price
    ) * 100

    support_distance = (
        (current_price - support) / current_price
    ) * 100

    if resistance == support:
        price_position = 50
    else:
        price_position = (
            (current_price - support) /
            (resistance - support)
        ) * 100

    closes = [format_candle(candle)["close"] for candle in candles]

    changes = []

    for i in range(1, len(closes)):
        changes.append(closes[i] - closes[i - 1])

    gains = [change for change in changes if change > 0]
    losses = [-change for change in changes if change < 0]

    average_gain = (
        sum(gains) / len(gains)
        if gains
        else 0
    )

    average_loss = (
        sum(losses) / len(losses)
        if losses
        else 0
    )

    score = 0
    score_reasons = []

    if average_loss == 0:
        rsi = 100
    else:
        rs = average_gain / average_loss
        rsi = 100 - (100 / (1 + rs))

    # Расчёт объёма покупателей и продавцов

    bullish_volume = 0
    bearish_volume = 0

    for candle in candles:
        data = format_candle(candle)

        if data["close"] > data["open"]:
            bullish_volume += data["volume"]

        elif data["close"] < data["open"]:
            bearish_volume += data["volume"]

    if bearish_volume == 0:
        volume_balance = 999
    else:
        volume_balance = bullish_volume / bearish_volume

    # =========================
    # 1. ТРЕНД
    # =========================

    if trend == "ВОСХОДЯЩИЙ":
        score += 1
        score_reasons.append("Тренд: +1")

    elif trend == "НИСХОДЯЩИЙ":
        score -= 1
        score_reasons.append("Тренд: -1")

    else:
        score_reasons.append("Тренд: 0")

    print(f"DEBUG SCORE {symbol} | После тренда: {score}")

    # =========================
    # 2. БЛИЗОСТЬ УРОВНЕЙ
    # =========================

    if trend == "ВОСХОДЯЩИЙ" and resistance_distance < 1:
        score -= 1
        score_reasons.append(
            "Сопротивление слишком близко: -1"
        )

    elif trend == "НИСХОДЯЩИЙ" and support_distance < 1:
        score += 1
        score_reasons.append(
            "Поддержка слишком близко: +1"
        )

    # =========================
    # 3. ПОЗИЦИЯ ЦЕНЫ В ДИАПАЗОНЕ
    # =========================

    if price_position < 30:

        if support_distance >= 1:
            score += 1
            score_reasons.append(
                "Цена ниже 30% диапазона: +1"
            )

    elif price_position >= 90:

        if resistance_distance >= 1:
            score -= 2
            score_reasons.append(
                "Цена выше 90% диапазона: -2"
            )

    elif price_position > 70:

        if resistance_distance >= 1:
            score -= 1
            score_reasons.append(
                "Цена выше 70% диапазона: -1"
            )

    print(f"DEBUG SCORE {symbol} | После позиции цены: {score}")

    # =========================
    # 4. RSI
    # =========================

    if rsi < 30:
        score += 1
        score_reasons.append(
            "RSI перепродан: +1"
        )

    elif rsi > 70:
        score -= 1
        score_reasons.append(
            "RSI перекуплен: -1"
        )

    print(f"DEBUG SCORE {symbol} | После RSI: {score}")

    # =========================
    # 5. ОБЪЁМ
    # =========================

    if volume_balance > 1.2:
        score += 1
        score_reasons.append(
            "Покупатели сильнее: +1"
        )

    elif volume_balance < 0.8:
        score -= 1
        score_reasons.append(
            "Продавцы сильнее: -1"
        )

    print(f"DEBUG SCORE {symbol} | После объёма: {score}")

    if score >= 2:
        signal = "LONG"
    elif score <= -2:
        signal = "SHORT"
    else:
        signal = "NO TRADE"

    initial_signal = signal

    trend_blocked = False

    if trend == "ВОСХОДЯЩИЙ" and signal == "SHORT":
        signal = "NO TRADE"
        trend_blocked = True

    elif trend == "НИСХОДЯЩИЙ" and signal == "LONG":
        signal = "NO TRADE"
        trend_blocked = True

    entry_price = current_price
    # Расчёт торговых уровней
    if signal == "LONG":
        stop_loss = support * 0.995
        take_profit = resistance

    elif signal == "SHORT":
        stop_loss = resistance * 1.005
        take_profit = support
    else:
        stop_loss = None
        take_profit = None
    print(
        f"DEBUG {symbol} | "
        f"Entry={entry_price} | "
        f"Resistance={resistance} | "
        f"Support={support} | "
        f"SL={stop_loss} | "
        f"TP={take_profit}"
    )

    # Сравнение уровней за последние 5 свечей
    if signal == "LONG":
        recent_stop_loss = recent_support * 0.995
        recent_take_profit = recent_resistance

    elif signal == "SHORT":
        recent_stop_loss = recent_resistance * 1.005
        recent_take_profit = recent_support

    else:
        recent_stop_loss = None
        recent_take_profit = None

    if signal in ["LONG", "SHORT"]:
        if signal == "LONG":
            recent_risk = entry_price - recent_stop_loss
            recent_reward = recent_take_profit - entry_price

        else:
            recent_risk = recent_stop_loss - entry_price
            recent_reward = entry_price - recent_take_profit

        if recent_risk > 0:
            recent_risk_reward = recent_reward / recent_risk
        else:
            recent_risk_reward = None

        if recent_risk is not None and entry_price > 0:
            recent_risk_percent = (
                recent_risk / entry_price
            ) * 100

            recent_reward_percent = (
                recent_reward / entry_price
            ) * 100

        else:
            recent_risk_percent = None
            recent_reward_percent = None
        print(
            f"DEBUG RECENT R:R {symbol} | "
            f"SL={recent_stop_loss} | "
            f"TP={recent_take_profit} | "
            f"R:R={recent_risk_reward} | "
            f"Risk={recent_risk_percent:.2f}% | "
            f"Reward={recent_reward_percent:.2f}%"
        )
    # Расчёт Risk/Reward

    if signal == "LONG":
        risk_amount = entry_price - stop_loss
        reward_amount = take_profit - entry_price

    elif signal == "SHORT":
        risk_amount = stop_loss - entry_price
        reward_amount = entry_price - take_profit

    else:
        risk_amount = None
        reward_amount = None

    # Процент риска и потенциальной прибыли

    if risk_amount is not None and entry_price > 0:
        risk_percent = (risk_amount / entry_price) * 100
        reward_percent = (reward_amount / entry_price) * 100
    else:
        risk_percent = None
        reward_percent = None

    # Расчёт Risk/Reward

    if (
        risk_amount is not None
        and risk_amount > 0
        and reward_amount is not None
    ):
        risk_reward = reward_amount / risk_amount
    else:
        risk_reward = None

    rr_blocked = False

    # Фильтр Risk/Reward

    if signal in ["LONG", "SHORT"]:
        if risk_reward is None or risk_reward < 1.5:
            signal = "NO TRADE"
            rr_blocked = True
            signal_reason = (
                "NO TRADE — недостаточное соотношение риск/прибыль"
            )

    if signal == "LONG":
        signal_reason = "Факторы сигнала LONG:\n"

        if trend == "НИСХОДЯЩИЙ":
            signal_reason += (
                "⚠️ Внимание: сигнал LONG против нисходящего тренда\n"
            )

        if trend == "ВОСХОДЯЩИЙ":
            signal_reason += "• Восходящий тренд\n"

        if rsi < 30:
            signal_reason += "• RSI показывает перепроданность\n"

        if volume_balance > 1.2:
            signal_reason += "• Объём покупателей сильнее\n"

        if price_position < 30:
            signal_reason += "• Цена находится ближе к поддержке\n"

        if resistance_distance < 1:
            signal_reason += "⚠️ Сопротивление слишком близко\n"

    elif signal == "SHORT":
        signal_reason = "Факторы сигнала SHORT:\n"

        if trend == "ВОСХОДЯЩИЙ":
            signal_reason += (
                "⚠️ Внимание: сигнал SHORT против восходящего тренда\n"
            )

        if trend == "НИСХОДЯЩИЙ":
            signal_reason += "• Нисходящий тренд\n"

        if rsi > 70:
            signal_reason += "• RSI показывает перекупленность\n"

        if volume_balance < 0.8:
            signal_reason += "• Объём продавцов сильнее\n"

        if price_position > 70:
            signal_reason += "• Цена находится ближе к сопротивлению\n"

        if support_distance < 1:
            signal_reason += "⚠️ Поддержка слишком близко\n"

    else:
        if rr_blocked:
            signal_reason = (
                "NO TRADE — недостаточное соотношение риск/прибыль"
            )

        elif trend_blocked:
            signal_reason = (
                f"NO TRADE — первоначальный сигнал {initial_signal} "
                "заблокирован фильтром тренда"
            )

        else:
            signal_reason = "NO TRADE — недостаточно подтверждений:"

            if trend == "ВОСХОДЯЩИЙ":
                signal_reason += "• Есть восходящий тренд\n"
            elif trend == "НИСХОДЯЩИЙ":
                signal_reason += "• Есть нисходящий тренд\n"
            else:
                signal_reason += "• Тренд боковой\n"

            if rsi < 30:
                signal_reason += "• RSI показывает перепроданность\n"
            elif rsi > 70:
                signal_reason += "• RSI показывает перекупленность\n"
            else:
                signal_reason += "• RSI не даёт сильного сигнала\n"

            if volume_balance > 1.2:
                signal_reason += "• Покупатели сильнее\n"
            elif volume_balance < 0.8:
                signal_reason += "• Продавцы сильнее\n"
            else:
                signal_reason += "• Объёмы примерно равны\n"

            if trend == "НИСХОДЯЩИЙ" and support_distance < 1:
                signal_reason += (
                    "⚠️ Поддержка слишком близко для SHORT\n"
                )

            elif trend == "ВОСХОДЯЩИЙ" and resistance_distance < 1:
                signal_reason += (
                    "⚠️ Сопротивление слишком близко для LONG\n"
                )

    if abs(score) == 0:
        confidence = 50

    elif abs(score) == 1:
        confidence = 60

    elif abs(score) == 2:
        confidence = 75

    else:
        confidence = 90
    if confidence >= 80:
        risk = "LOW"

    elif confidence >= 60:
        risk = "MEDIUM"

    else:
        risk = "HIGH"

    # Если сделка заблокирована фильтром Risk/Reward
    if rr_blocked:
        confidence = 50
        risk = "HIGH"

    reasons = []

    if trend == "ВОСХОДЯЩИЙ":
        reasons.append("🟢 Тренд восходящий")

    elif trend == "НИСХОДЯЩИЙ":
        reasons.append("🔴 Тренд нисходящий")

    else:
        reasons.append("⚪ Тренд боковой")
    if rsi < 30:
        reasons.append("🟢 RSI показывает перепроданность")

    elif rsi > 70:
        reasons.append("🔴 RSI показывает перекупленность")

    else:
        reasons.append("⚪ RSI в нейтральной зоне")

    if price_position < 30:
        reasons.append("📍 Цена находится близко к поддержке")
    elif price_position > 70:
        reasons.append("📍 Цена находится близко к сопротивлению")
    else:
        reasons.append("⚪ Цена находится в середине диапазона")

    if trend == "ВОСХОДЯЩИЙ" and resistance_distance < 1:
        reasons.append("⚠️ Сопротивление слишком близко — LONG ограничен")

    elif trend == "НИСХОДЯЩИЙ" and support_distance < 1:
        reasons.append("⚠️ Поддержка слишком близко — SHORT ограничен")

    if volume_balance > 1.2:
        reasons.append("🟢 Объём покупателей сильнее")

    elif volume_balance < 0.8:
        reasons.append("🔴 Объём продавцов сильнее")

    else:
        reasons.append("⚪ Объёмы примерно равны")

    signal_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "symbol": symbol,
        "signal_time": signal_time,
        "trend": trend,
        "resistance": resistance,
        "support": support,
        "resistance_distance": round(resistance_distance, 2),
        "support_distance": round(support_distance, 2),
        "price_position": round(price_position, 2),
        "rsi": round(rsi, 2),
        "volume_balance": round(volume_balance, 2),
        "score": score,
        "signal": signal,
        "initial_signal": initial_signal,
        "entry_price": round(entry_price, 5),
        "stop_loss": round(stop_loss, 5) if stop_loss is not None else None,
        "take_profit": round(take_profit, 5) if take_profit is not None else None,
        "risk_reward": round(risk_reward, 2) if risk_reward is not None else None,
        "risk_percent": round(risk_percent, 2) if risk_percent is not None else None,
        "reward_percent": round(reward_percent, 2) if reward_percent is not None else None,
        "signal_reason": signal_reason,
        "trend_blocked": trend_blocked,
        "rr_blocked": rr_blocked,
        "confidence": confidence,
        "risk": risk,
        "reasons": reasons,
        "score_reasons": score_reasons,
        "candles": candles
    }


def format_analysis(result):
    text = ""

    text += f"📊 Анализ {result['symbol']}\n\n"
    text += f"📈 Тренд: {result['trend']}\n"
    text += f"📉 RSI: {result['rsi']}\n"
    text += f"🔴 Сопротивление: {result['resistance']} USDT\n"
    text += f"🟢 Поддержка: {result['support']} USDT\n"
    text += f"📏 До сопротивления: {result['resistance_distance']} %\n"
    text += f"📏 До поддержки: {result['support_distance']} %\n"
    text += f"📊 Позиция в диапазоне: {result['price_position']} %\n"
    text += f"⚖️ Баланс объёма: {result['volume_balance']}\n\n"

    text += f"📊 Оценка: {result['score']}\n"

    if result["initial_signal"] != "NO TRADE":
        text += f"🎯 Первоначальный сигнал: {result['initial_signal']}\n"

    text += f"🎯 Сигнал: {result['signal']}\n"

    if result["signal"] in ["LONG", "SHORT"]:
        text += f"💵 Entry: {result['entry_price']} USDT\n"
        text += (
            f"🛑 Stop Loss: {result['stop_loss']} USDT "
            f"({result['risk_percent']}%)\n"
        )
        text += (
            f"🎯 Take Profit: {result['take_profit']} USDT "
            f"({result['reward_percent']}%)\n"
        )
        text += f"⚖️ Risk/Reward: 1 : {result['risk_reward']}\n"

    elif result["initial_signal"] in ["LONG", "SHORT"]:

        text += f"⚖️ Risk/Reward: 1 : {result['risk_reward']}\n"

        if result["trend_blocked"]:
            text += (
                f"🚫 Сделка заблокирована фильтром тренда "
                f"({result['trend']})\n"
            )

        elif result["rr_blocked"]:
            text += "🚫 Сделка заблокирована фильтром R:R\n"

        else:
            text += "🚫 Сделка заблокирована\n"

    text += f"💡 Причина сигнала: {result['signal_reason']}\n"
    text += f"📈 Уверенность: {result['confidence']} %\n"
    text += f"⚠️ Риск: {result['risk']}\n\n"

    text += "Причины:\n"

    for reason in result["reasons"]:
        text += f"{reason}\n"

    return text


if __name__ == "__main__":
    result = analyze_market("BTCUSDT", "15m", 15)

    print()
    print("Проверка analyze_market:")
    print("Символ:", result["symbol"])
    print("Тренд:", result["trend"])
    print("RSI:", result["rsi"])
    print("Баланс объёма:", result["volume_balance"])
    print("Позиция в диапазоне:", result["price_position"], "%")
    print("Оценка:", result["score"])
    print("Сигнал:", result["signal"])
    print("Уверенность:", result["confidence"], "%")
    print("Риск:", result["risk"])
    print("Entry:", result["entry_price"])
    print("Stop Loss:", result["stop_loss"])
    print("Take Profit:", result["take_profit"])

    print()
    print("Проверка форматирования:")
    print(format_analysis(result))


def scan_market():
    symbols = get_top_volume_symbols(30)

    results = []
    no_trade_results = []
    rejected_results = []

    for symbol in symbols:
        try:
            print(f"\nАнализируем {symbol}...")

            result = analyze_market(symbol, "15m", 15)

            signal = result["signal"]
            initial_signal = result["initial_signal"]
            trend = result["trend"]
            trend_1h = get_1h_trend(symbol)
            score = result["score"]
            risk_reward = result["risk_reward"]
            score_reasons = result["score_reasons"]
            signal_time = result["signal_time"]

            entry_price = result["entry_price"]
            stop_loss = result["stop_loss"]
            take_profit = result["take_profit"]
            risk_percent = result["risk_percent"]
            reward_percent = result["reward_percent"]

            print(
                f"{symbol} | "
                f"Тренд: {trend} | "
                f"Время: {signal_time} | "
                f"Первоначальный сигнал: {initial_signal} | "
                f"Итоговый сигнал: {signal} | "
                f"Score: {score} | "
                f"R:R: {risk_reward}\n"
                f"Entry: {result['entry_price']} | "
                f"SL: {result['stop_loss']} | "
                f"TP: {result['take_profit']}\n"
                f"До сопротивления: "
                f"{result['resistance_distance']}% | "
                f"До поддержки: "
                f"{result['support_distance']}% | "
                f"Позиция цены: "
                f"{result['price_position']}%"
            )
            print("Причины Score:")

            for reason in score_reasons:
                print(f"  • {reason}")
            if initial_signal in ["LONG", "SHORT"] and signal == "NO TRADE":

                if result["trend_blocked"]:
                    print(
                        f"⚠️ {symbol} — сигнал {initial_signal} "
                        f"отклонён фильтром тренда. "
                        f"Тренд: {result['trend']}"
                    )

                elif result["rr_blocked"]:
                    print(
                        f"⚠️ {symbol} — сигнал {initial_signal} "
                        f"отклонён из-за R:R: {risk_reward}"
                    )

                else:
                    print(
                        f"⚠️ {symbol} — сигнал {initial_signal} "
                        f"отклонён."
                    )
                rejected_results.append({
                    "symbol": symbol,
                    "signal": initial_signal,
                    "score": score,
                    "risk_reward": risk_reward,
                    "entry_price": result["entry_price"],
                    "stop_loss": result["stop_loss"],
                    "take_profit": result["take_profit"],
                    "resistance": result["resistance"],
                    "support": result["support"],
                    "resistance_distance": result["resistance_distance"],
                    "support_distance": result["support_distance"],
                    "trend": result["trend"],
                    "rsi": result["rsi"],
                    "volume_balance": result["volume_balance"],
                    "signal_reason": result["signal_reason"],
                })

                continue

            if signal not in ["LONG", "SHORT"]:
                print(f"❌ {symbol} — нет торгового сигнала")

                if len(no_trade_results) < 10:
                    no_trade_results.append({
                        "symbol": symbol,
                        "score": score,
                        "trend": result["trend"],
                        "rsi": result["rsi"],
                        "volume_balance": result["volume_balance"],
                        "signal_reason": result["signal_reason"],
                    })

                continue

            if risk_reward is None:
                print(f"❌ {symbol} — R:R отсутствует")
                continue

            if risk_reward < 1.5:
                print(
                    f"❌ {symbol} — "
                    f"R:R слишком низкий: {risk_reward}"
                )
                continue
            if has_active_signal(symbol, signal):
                print(
                    f"⏭️ {symbol} — "
                    f"{signal} уже есть среди активных сигналов"
                )
                continue

            signal_record = {
                "signal_time": signal_time,
                "symbol": symbol,
                "initial_signal": initial_signal,
                "signal": signal,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "score": score,
                "trend_1h": trend_1h,
                "risk_reward": risk_reward,
                "risk_percent": risk_percent,
                "reward_percent": reward_percent,
                "confidence": result["confidence"],
                "status": "ACTIVE",
                "result": None
            }

            save_signal(signal_record)

            print(f"✅ {symbol} — сигнал сохранён в tracker")

            results.append({
                "symbol": symbol,
                "signal_time": signal_time,
                "signal": signal,
                "score": score,
                "risk_reward": risk_reward,
                "entry_price": result["entry_price"],
                "stop_loss": result["stop_loss"],
                "take_profit": result["take_profit"],
                "risk_percent": result["risk_percent"],
                "reward_percent": result["reward_percent"],
                "trend": result["trend"],
                "trend_1h": trend_1h,
                "rsi": result["rsi"],
                "volume_balance": result["volume_balance"],
                "confidence": result["confidence"],
                "risk": result["risk"],
                "signal_reason": result["signal_reason"],
            })

        except Exception as error:
            print(f"⚠️ Ошибка {symbol}: {error}")

    print(f"\nВсего найдено сигналов: {len(results)}")

    print(
        f"Всего NO TRADE: {len(no_trade_results)}"
    )

    print(
        f"Всего отклонённых сигналов: {len(rejected_results)}"
    )
    return {
        "signals": results,
        "no_trade": no_trade_results,
        "rejected": rejected_results
    }


if __name__ == "__main__":
    scan_result = scan_market()

    signals = scan_result["signals"]

    print("\n=== НАЙДЕННЫЕ СИГНАЛЫ ===")

    if not signals:
        print("Подходящих сигналов нет.")

    else:
        for signal in signals:
            print(
                signal["symbol"],
                "|",
                signal["signal"],
                "| Score:",
                signal["score"],
                "| R:R:",
                signal["risk_reward"]
            )
