import httpx


def get_price(symbol):
    url = "https://fapi.binance.com/fapi/v1/ticker/price"

    response = httpx.get(
        url,
        params={"symbol": symbol},
        timeout=10.0
    )

    response.raise_for_status()

    data = response.json()

    return float(data["price"])


def get_klines(symbol, interval="1m", limit=100):
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
        return "bullish"

    elif candle["close"] < candle["open"]:
        return "bearish"

    else:
        return "neutral"


def candle_body_size(candle):
    return abs(candle["close"] - candle["open"])


def upper_wick_size(candle):
    return candle["high"] - max(
        candle["open"],
        candle["close"]
    )


def lower_wick_size(candle):
    return min(
        candle["open"],
        candle["close"]
    ) - candle["low"]


def candle_range_size(candle):
    return candle["high"] - candle["low"]


def candle_body_percent(candle):
    candle_range = candle_range_size(candle)

    if candle_range == 0:
        return 0

    body = candle_body_size(candle)

    return (body / candle_range) * 100


def body_to_range_ratio(candle):
    candle_range = candle_range_size(candle)

    if candle_range == 0:
        return 0

    body = candle_body_size(candle)

    return body / candle_range


def body_to_wicks_ratio(candle):
    body = candle_body_size(candle)

    upper_wick = upper_wick_size(candle)
    lower_wick = lower_wick_size(candle)

    total_wicks = upper_wick + lower_wick

    if total_wicks == 0:
        return 0

    return body / total_wicks


def body_to_wicks_label(ratio):
    if ratio < 0.5:
        return "wicks_dominant"

    elif ratio < 1.0:
        return "balanced"

    elif ratio < 2.0:
        return "body_dominant"

    else:
        return "strong_body_dominant"


def candle_body_dominance_signal(candle):
    ratio = body_to_wicks_ratio(candle)
    direction = candle_direction(candle)

    if ratio >= 2.0:
        if direction == "bullish":
            return "strong_bullish_body"

        elif direction == "bearish":
            return "strong_bearish_body"

    elif ratio >= 1.0:
        if direction == "bullish":
            return "bullish_body"

        elif direction == "bearish":
            return "bearish_body"

    return "weak_body"


def candle_strength_signal(candle):
    direction = candle_direction(candle)
    ratio = body_to_wicks_ratio(candle)

    if direction == "bullish":
        if ratio >= 2.0:
            return "strong_bullish"

        elif ratio >= 1.0:
            return "bullish"

        else:
            return "weak_bullish"

    elif direction == "bearish":
        if ratio >= 2.0:
            return "strong_bearish"

        elif ratio >= 1.0:
            return "bearish"

        else:
            return "weak_bearish"

    else:
        return "neutral"


def candle_structure_signal(candle):
    direction = candle_direction(candle)
    strength = candle_strength_signal(candle)
    wick = long_wick_direction(candle)

    if direction == "bullish":
        if strength == "strong_bullish" and wick == "none":
            return "strong_bullish"

        elif wick == "upper":
            return "bullish_with_rejection"

        elif wick == "lower":
            return "bullish_with_support"

        else:
            return "bullish"

    elif direction == "bearish":
        if strength == "strong_bearish" and wick == "none":
            return "strong_bearish"

        elif wick == "upper":
            return "bearish_with_rejection"

        elif wick == "lower":
            return "bearish_with_support"

        else:
            return "bearish"

    else:
        return "neutral"


def body_size_label(ratio):
    if ratio < 0.1:
        return "very_small"

    elif ratio < 0.25:
        return "small"

    elif ratio < 0.5:
        return "normal"

    elif ratio < 0.75:
        return "large"

    else:
        return "very_large"


def is_doji_like(candle):
    ratio = body_to_range_ratio(candle)

    return ratio < 0.1


def candle_pattern_type(candle):
    ratio = body_to_range_ratio(candle)

    upper = upper_wick_percent(candle)
    lower = lower_wick_percent(candle)

    if ratio < 0.1 and upper >= 40 and lower >= 40:
        return "doji"

    elif ratio < 0.25 and lower >= 40:
        return "long_lower_wick"

    elif ratio < 0.25 and upper >= 40:
        return "long_upper_wick"

    elif ratio >= 0.5 and upper < 25 and lower < 25:
        return "strong_body"

    else:
        return "normal"


def upper_wick_percent(candle):
    candle_range = candle_range_size(candle)

    if candle_range == 0:
        return 0

    upper_wick = upper_wick_size(candle)

    return (upper_wick / candle_range) * 100


def lower_wick_percent(candle):
    candle_range = candle_range_size(candle)

    if candle_range == 0:
        return 0

    lower_wick = lower_wick_size(candle)

    return (lower_wick / candle_range) * 100


def wick_strength(wick_percent):
    if wick_percent < 10:
        return "very_small"

    elif wick_percent < 25:
        return "small"

    elif wick_percent < 40:
        return "normal"

    elif wick_percent < 60:
        return "large"

    else:
        return "very_large"


def upper_wick_strength(candle):
    percent = upper_wick_percent(candle)

    return wick_strength(percent)


def lower_wick_strength(candle):
    percent = lower_wick_percent(candle)

    return wick_strength(percent)


def has_long_lower_wick(candle):
    percent = lower_wick_percent(candle)

    return percent >= 40


def has_long_upper_wick(candle):
    percent = upper_wick_percent(candle)

    return percent >= 40


def long_wick_direction(candle):
    upper = has_long_upper_wick(candle)
    lower = has_long_lower_wick(candle)

    if upper and lower:
        return "both"

    elif upper:
        return "upper"

    elif lower:
        return "lower"

    else:
        return "none"


def full_candle_structure(candle):
    return {
        "body": candle_body_size(candle),
        "body_percent": candle_body_percent(candle),
        "body_to_range_ratio": body_to_range_ratio(candle),
        "body_to_wicks_ratio": body_to_wicks_ratio(candle),
        "body_to_wicks_label": body_to_wicks_label(
            body_to_wicks_ratio(candle)
        ),
        "body_dominance_signal": candle_body_dominance_signal(candle),
        "strength_signal": candle_strength_signal(candle),
        "structure_signal": candle_structure_signal(candle),
        "final_signal": candle_final_signal(candle),
        "body_size_label": body_size_label(
            body_to_range_ratio(candle)
        ),
        "is_doji_like": is_doji_like(candle),
        "pattern_type": candle_pattern_type(candle),
        "upper_wick": upper_wick_size(candle),
        "upper_wick_percent": upper_wick_percent(candle),
        "upper_wick_strength": upper_wick_strength(candle),
        "lower_wick": lower_wick_size(candle),
        "lower_wick_percent": lower_wick_percent(candle),
        "lower_wick_strength": lower_wick_strength(candle),
        "range": candle_range_size(candle)
    }


def analyze_last_candle_complete(candles):
    last_candle = get_last_candle(candles)

    direction = candle_direction(last_candle)

    structure = full_candle_structure(last_candle)

    summary = analyze_candle_summary(last_candle)

    return {
        "direction": direction,
        "structure": structure,
        "summary": summary
    }


def analyze_price_range_complete(candles, current_price):
    highest_price, lowest_price = get_price_range(candles)

    position = range_position(
        current_price,
        highest_price,
        lowest_price
    )

    distance_to_high, distance_to_low = price_distances(
        current_price,
        highest_price,
        lowest_price
    )

    closest_level = closer_to_level(
        distance_to_high,
        distance_to_low
    )

    to_high_percent, to_low_percent = distance_percent(
        current_price,
        highest_price,
        lowest_price
    )

    position_label = price_position_label(position)

    support, resistance = get_support_resistance(
        highest_price,
        lowest_price
    )

    support_percent, resistance_percent = (
        support_resistance_distance(
            current_price,
            support,
            resistance
        )
    )

    return {
        "highest_price": highest_price,
        "lowest_price": lowest_price,
        "position": position,
        "distance_to_high": distance_to_high,
        "distance_to_low": distance_to_low,
        "closest_level": closest_level,
        "to_high_percent": to_high_percent,
        "to_low_percent": to_low_percent,
        "position_label": position_label,
        "support": support,
        "resistance": resistance,
        "support_percent": support_percent,
        "resistance_percent": resistance_percent
    }


def analyze_candle_summary(candle):
    direction = candle_direction(candle)
    strength = candle_strength_signal(candle)
    structure = candle_structure_signal(candle)
    pattern = candle_pattern_type(candle)
    wick = long_wick_direction(candle)
    final_signal = candle_final_signal(candle)

    return {
        "direction": direction,
        "strength": strength,
        "structure": structure,
        "pattern": pattern,
        "wick": wick,
        "final_signal": final_signal
    }


def candle_final_signal(candle):
    direction = candle_direction(candle)
    strength = candle_strength_signal(candle)
    wick = long_wick_direction(candle)

    if direction == "bullish":
        if strength == "strong_bullish" and wick == "none":
            return "strong_bullish"

        elif wick == "upper":
            return "bullish_rejection"

        elif wick == "lower":
            return "bullish_support"

        else:
            return "bullish"

    elif direction == "bearish":
        if strength == "strong_bearish" and wick == "none":
            return "strong_bearish"

        elif wick == "upper":
            return "bearish_rejection"

        elif wick == "lower":
            return "bearish_support"

        else:
            return "bearish"

    else:
        return "neutral"


def candle_direction_sequence(candles):
    sequence = []

    for candle in candles:
        formatted = format_candle(candle)
        direction = candle_direction(formatted)

        sequence.append(direction)

    return sequence


def current_candle_streak(candles):
    sequence = candle_direction_sequence(candles)

    if not sequence:
        return "neutral", 0

    current_direction = sequence[-1]
    streak = 1

    for direction in reversed(sequence[:-1]):
        if direction == current_direction:
            streak += 1
        else:
            break

    return current_direction, streak


def streak_strength(streak_length):
    if streak_length >= 5:
        return "very_strong"

    elif streak_length >= 3:
        return "strong"

    elif streak_length == 2:
        return "moderate"

    else:
        return "weak"


def streak_percent(streak_length, total_candles):
    if total_candles == 0:
        return 0

    return (streak_length / total_candles) * 100


def streak_percent_label(percent):
    if percent >= 50:
        return "very_significant"

    elif percent >= 30:
        return "significant"

    elif percent >= 20:
        return "moderate"

    elif percent >= 10:
        return "small"

    else:
        return "very_small"


def analyze_candle_streak(candles):
    direction, length = current_candle_streak(candles)

    strength = streak_strength(length)

    percent = streak_percent(
        length,
        len(candles)
    )

    percent_label = streak_percent_label(percent)

    return {
        "direction": direction,
        "length": length,
        "strength": strength,
        "percent": percent,
        "percent_label": percent_label
    }


def analyze_streak_alignment(candles):
    streak = analyze_candle_streak(candles)

    direction_analysis = candle_direction_analysis(candles)

    alignment = streak_alignment(
        direction_analysis["direction"],
        streak["direction"]
    )

    return {
        "overall_direction": direction_analysis["direction"],
        "streak_direction": streak["direction"],
        "alignment": alignment
    }


def analyze_streak_complete(candles):
    streak = analyze_candle_streak(candles)

    alignment = analyze_streak_alignment(candles)

    return {
        "direction": streak["direction"],
        "length": streak["length"],
        "strength": streak["strength"],
        "percent": streak["percent"],
        "percent_label": streak["percent_label"],
        "overall_direction": alignment["overall_direction"],
        "alignment": alignment["alignment"]
    }


def streak_alignment(
    overall_direction,
    streak_direction
):
    if (
        overall_direction == "neutral"
        or streak_direction == "neutral"
    ):
        return "neutral"

    if overall_direction == streak_direction:
        return "aligned"

    return "opposite"


def candle_direction_percent(candles):
    bullish, bearish, neutral = count_candle_directions(candles)

    total = bullish + bearish + neutral

    if total == 0:
        return 0, 0, 0

    bullish_percent = (bullish / total) * 100
    bearish_percent = (bearish / total) * 100
    neutral_percent = (neutral / total) * 100

    return (
        bullish_percent,
        bearish_percent,
        neutral_percent
    )


def dominant_candle_direction(bullish_percent, bearish_percent):
    if bullish_percent > bearish_percent:
        return "bullish"

    elif bearish_percent > bullish_percent:
        return "bearish"

    else:
        return "neutral"


def dominant_candle_strength(bullish_percent, bearish_percent):
    difference = abs(
        bullish_percent - bearish_percent
    )

    if difference >= 50:
        return "very_strong"

    elif difference >= 30:
        return "strong"

    elif difference >= 15:
        return "moderate"

    elif difference >= 5:
        return "weak"

    else:
        return "neutral"


def candle_direction_analysis(candles):
    bullish_percent, bearish_percent, neutral_percent = (
        candle_direction_percent(candles)
    )

    direction = dominant_candle_direction(
        bullish_percent,
        bearish_percent
    )

    strength = dominant_candle_strength(
        bullish_percent,
        bearish_percent
    )

    return {
        "bullish_percent": bullish_percent,
        "bearish_percent": bearish_percent,
        "neutral_percent": neutral_percent,
        "direction": direction,
        "strength": strength
    }


def analyze_candle_direction_complete(candles):
    analysis = candle_direction_analysis(candles)

    return {
        "bullish_percent": analysis["bullish_percent"],
        "bearish_percent": analysis["bearish_percent"],
        "neutral_percent": analysis["neutral_percent"],
        "direction": analysis["direction"],
        "strength": analysis["strength"]
    }


def count_candle_directions(candles):
    bullish = 0
    bearish = 0
    neutral = 0

    for candle in candles:
        formatted = format_candle(candle)
        direction = candle_direction(formatted)

        if direction == "bullish":
            bullish += 1

        elif direction == "bearish":
            bearish += 1

        else:
            neutral += 1

    return bullish, bearish, neutral


def volume_stats(candles):
    volumes = [float(candle[5]) for candle in candles]

    total_volume = sum(volumes)
    average_volume = total_volume / len(volumes)

    return total_volume, average_volume


def last_volume_stats(candles):
    last_volume = float(candles[-1][5])

    total_volume, average_volume = volume_stats(candles)

    if average_volume == 0:
        ratio = 0
    else:
        ratio = last_volume / average_volume

    return last_volume, ratio


def volume_level(ratio):
    if ratio >= 1.5:
        return "high"

    elif ratio >= 0.8:
        return "normal"

    else:
        return "low"


def volume_strength(ratio):
    if ratio < 0.3:
        return "very_low"

    elif ratio < 0.8:
        return "low"

    elif ratio < 1.2:
        return "normal"

    elif ratio < 2.0:
        return "high"

    else:
        return "very_high"


def volume_change_percent(ratio):
    return round((ratio - 1) * 100, 2)


def bullish_bearish_volume(candles):
    bullish_volume = 0
    bearish_volume = 0

    for candle in candles:
        formatted = format_candle(candle)
        direction = candle_direction(formatted)

        if direction == "bullish":
            bullish_volume += formatted["volume"]

        elif direction == "bearish":
            bearish_volume += formatted["volume"]

    return bullish_volume, bearish_volume


def volume_balance(bullish_volume, bearish_volume):
    if bearish_volume == 0:
        return 0

    return bullish_volume / bearish_volume


def volume_direction(ratio):
    if ratio >= 1.2:
        return "bullish"

    elif ratio <= 0.8:
        return "bearish"

    else:
        return "neutral"


def volume_direction_strength(ratio):
    if ratio >= 2.0:
        return "strong_bullish"

    elif ratio >= 1.2:
        return "bullish"

    elif ratio > 0.8:
        return "neutral"

    elif ratio > 0.5:
        return "bearish"

    else:
        return "strong_bearish"


def analyze_volume(candles):
    total_volume, average_volume = volume_stats(candles)

    last_volume, volume_ratio = last_volume_stats(candles)

    level = volume_level(volume_ratio)

    strength = volume_strength(volume_ratio)

    change_percent = volume_change_percent(volume_ratio)

    bullish_volume, bearish_volume = bullish_bearish_volume(candles)

    balance = volume_balance(
        bullish_volume,
        bearish_volume
    )

    direction = volume_direction(balance)
    direction_strength = volume_direction_strength(balance)

    return {
        "total_volume": total_volume,
        "average_volume": average_volume,
        "last_volume": last_volume,
        "volume_ratio": volume_ratio,
        "volume_level": level,
        "volume_strength": strength,
        "volume_change_percent": change_percent,
        "bullish_volume": bullish_volume,
        "bearish_volume": bearish_volume,
        "volume_balance": balance,
        "volume_direction": direction,
        "volume_direction_strength": direction_strength
    }


def get_last_candle(candles):
    return format_candle(candles[-1])


def get_price_range(candles):
    highs = [float(candle[2]) for candle in candles]
    lows = [float(candle[3]) for candle in candles]

    highest_price = max(highs)
    lowest_price = min(lows)

    return highest_price, lowest_price


def range_position(current_price, highest_price, lowest_price):
    price_range = highest_price - lowest_price

    if price_range == 0:
        return 0

    position = ((current_price - lowest_price) / price_range) * 100

    return position


def price_distances(current_price, highest_price, lowest_price):
    distance_to_high = highest_price - current_price
    distance_to_low = current_price - lowest_price

    return distance_to_high, distance_to_low


def closer_to_level(distance_to_high, distance_to_low):
    if distance_to_high < distance_to_low:
        return "high"

    elif distance_to_low < distance_to_high:
        return "low"

    else:
        return "equal"


def distance_percent(current_price, highest_price, lowest_price):
    price_range = highest_price - lowest_price

    if price_range == 0:
        return 0, 0

    to_high_percent = (
        (highest_price - current_price) / price_range
    ) * 100

    to_low_percent = (
        (current_price - lowest_price) / price_range
    ) * 100

    return to_high_percent, to_low_percent


def price_position_label(position):
    if position <= 25:
        return "near_low"

    elif position >= 75:
        return "near_high"

    else:
        return "middle"


def get_support_resistance(highest_price, lowest_price):
    support = lowest_price
    resistance = highest_price

    return support, resistance


def support_resistance_distance(current_price, support, resistance):
    price_range = resistance - support

    if price_range == 0:
        return 0, 0

    distance_to_support = (
        (current_price - support) / price_range
    ) * 100

    distance_to_resistance = (
        (resistance - current_price) / price_range
    ) * 100

    return distance_to_support, distance_to_resistance


def get_ema50(symbol, interval="1h", limit=50):
    candles = get_klines(symbol, interval, limit)

    closes = [
        float(candle[4])
        for candle in candles
    ]

    multiplier = 2 / (50 + 1)

    ema = closes[0]

    for price in closes[1:]:
        ema = (price - ema) * multiplier + ema

    return ema


def get_1h_trend(symbol):
    candles = get_klines(symbol, "1h", 50)

    current_price = float(candles[-1][4])
    ema50 = get_ema50(symbol, "1h", 50)

    if current_price > ema50:
        return "UP"

    elif current_price < ema50:
        return "DOWN"

    return "NEUTRAL"
