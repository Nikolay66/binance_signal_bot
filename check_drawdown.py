
from datetime import datetime
import json

with open("signals.json", "r", encoding="utf-8") as file:
    signals = json.load(file)

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
    if signal["result"] == "TP":
        cumulative_r += signal.get("risk_reward", 0)
    else:
        cumulative_r -= 1

    peak_r = max(peak_r, cumulative_r)
    drawdown = peak_r - cumulative_r
    max_drawdown_r = max(max_drawdown_r, drawdown)

print("Завершённых сделок:", len(finished_signals))
print("Итоговый результат:", round(cumulative_r, 2), "R")
print("Максимальная просадка:", round(max_drawdown_r, 2), "R")

missing_time = sum(
    1 for signal in signals
    if signal.get("result") in ("TP", "SL")
    and not signal.get("result_time")
)

print("Завершённых сигналов без result_time:", missing_time)
print(
    "Завершённых по результату:",
    sum(
        1 for signal in signals
        if signal.get("result") in ("TP", "SL")
    )
)

print(
    "Завершённых с временем закрытия:",
    len(finished_signals)
)
missing_signal_time = sum(
    1 for signal in signals
    if signal.get("result") in ("TP", "SL")
    and not signal.get("signal_time")
)

missing_result_time = sum(
    1 for signal in signals
    if signal.get("result") in ("TP", "SL")
    and not signal.get("result_time")
)

print("Без signal_time:", missing_signal_time)
print("Без result_time:", missing_result_time)


total_duration = 0

for signal in finished_signals:
    start = datetime.strptime(
        signal["signal_time"],
        "%Y-%m-%d %H:%M:%S"
    )

    end = datetime.strptime(
        signal["result_time"],
        "%Y-%m-%d %H:%M:%S"
    )

    total_duration += (end - start).total_seconds()

average_seconds = total_duration / len(finished_signals)

print("Средняя длительность, секунд:", round(average_seconds, 2))
print("Средняя длительность, часов:", round(average_seconds / 3600, 2))
