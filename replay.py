#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
replay.py - перепроигрывает сигналы бота по 1-минутным свечам Binance Futures.

Что делает:
  1. Скачивает 1m-свечи по каждому сигналу из signals.json (кэш на диске).
  2. Проверяет TP/SL по high/low свечей (а не по цене раз в минуту, как tracker.py)
     и сверяет результат с тем, что записал tracker.
  3. Считает MAE/MFE: как далеко цена шла в вашу пользу перед стопом и
     насколько близко к стопу подходили сделки, закрывшиеся по тейку.
  4. Прогоняет варианты управления сделкой на тех же данных:
     TP на 60-90% пути, перенос стопа в безубыток, SL от ATR, тайм-стоп.
  5. Печатает статистику по фильтрам (риск %, RR, риск в ATR) и пишет CSV.

Запуск:
  pip install httpx
  python replay.py --signals signals.json --limit 40     # быстрая проверка
  python replay.py --signals signals.json                # полный прогон

Часовой пояс signal_time определяется автоматически (по цене входа), либо
задайте его вручную: --tz 3 | --tz Europe/Moscow | --tz UTC | --tz local

Допущения (меняются аргументами): комиссия 0.08% за круг (--fee), проскальзывание
0 (--slip, % на сторону), если в одной минутной свече задеты и SL, и TP - считаем,
что сработал SL (--ambiguous sl|tp). Результаты - оценка на истории,
а не гарантия и не финансовая рекомендация.
"""

import argparse
import bisect
import csv
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median, pstdev
from urllib.parse import quote

MIN = 60_000
HOUR = 60 * MIN
API = "https://fapi.binance.com/fapi/v1/klines"
TS_FMT = "%Y-%m-%d %H:%M:%S"
PAD_LEFT = 5 * HOUR  # запас слева для расчёта ATR(15m)


# ----------------------------------------------------------------------------
# Загрузка данных
# ----------------------------------------------------------------------------

class SymbolError(Exception):
    pass


class Fetcher:
    def __init__(self, cache_dir="kline_cache", pause=0.12):
        import httpx
        self.httpx = httpx
        self.client = httpx.Client(timeout=30.0)
        self.cache_dir = cache_dir
        self.pause = pause
        os.makedirs(cache_dir, exist_ok=True)

    def _get(self, params):
        for attempt in range(8):
            try:
                r = self.client.get(API, params=params)
            except self.httpx.HTTPError:
                time.sleep(min(2 ** attempt, 30))
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in (418, 429):
                wait = int(r.headers.get("Retry-After", "30")) + 1
                print(f"  лимит API, жду {wait} с...")
                time.sleep(wait)
                continue
            if r.status_code == 400:
                raise SymbolError(r.text[:200])
            time.sleep(min(2 ** attempt, 30))
        raise RuntimeError("Binance не отвечает (8 попыток подряд)")

    def klines(self, symbol, start, end):
        """1m-свечи [start, end) -> список [open_time, o, h, l, c]."""
        now = int(time.time() * 1000) // MIN * MIN
        end = min(end, now)
        if end <= start:
            return []
        path = os.path.join(
            self.cache_dir, f"{quote(symbol, safe='')}_{start}_{end}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)

        rows = []
        cur = start
        while cur < end:
            data = self._get({
                "symbol": symbol, "interval": "1m",
                "startTime": cur, "endTime": end - 1, "limit": 1500,
            })
            if not data:
                break
            rows += [[int(k[0]), float(k[1]), float(k[2]),
                      float(k[3]), float(k[4])] for k in data]
            nxt = int(data[-1][0]) + MIN
            if nxt <= cur or len(data) < 1500:
                break
            cur = nxt
            time.sleep(self.pause)
        time.sleep(self.pause)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f)
        return rows


# ----------------------------------------------------------------------------
# Время
# ----------------------------------------------------------------------------

def naive_ms(text):
    """'2026-10-01 12:00:00' как UTC -> миллисекунды."""
    dt = datetime.strptime(text, TS_FMT).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def detect_tz(sigs, fetcher, n_samples=12, tol=0.0002):
    """Подбирает смещение часового пояса (целые часы) по цене входа."""
    step = max(1, len(sigs) // n_samples)
    sample = sigs[::step][:n_samples]
    scores = {off: 0 for off in range(-11, 14)}
    used = 0
    for s in sample:
        ms0 = naive_ms(s["signal_time"])
        start = ms0 - 13 * HOUR
        try:
            rows = fetcher.klines(s["symbol"], start, start + 1500 * MIN)
        except SymbolError:
            continue
        if not rows:
            continue
        used += 1
        T = [r[0] for r in rows]
        for off in scores:
            true_ms = ms0 - off * HOUR
            i1 = bisect.bisect_right(T, true_ms)
            seg = rows[max(0, i1 - 2):i1]
            if not seg:
                continue
            lo = min(r[3] for r in seg)
            hi = max(r[2] for r in seg)
            if lo * (1 - tol) <= s["entry_price"] <= hi * (1 + tol):
                scores[off] += 1
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, second = ranked[0], ranked[1]
    ok = (used >= 5 and best[1] >= 0.7 * used
          and best[1] - second[1] >= max(2, 0.2 * used))
    return best[0], ok, used, ranked[:3]


def make_tz_converter(tz_arg, sigs, fetcher):
    if tz_arg == "auto":
        off, ok, used, top = detect_tz(sigs, fetcher)
        print(f"Определение часового пояса: образцов {used}, "
              f"лучшие варианты (UTC+часы, совпадений): {top}")
        if not ok:
            print("Не удалось надёжно определить часовой пояс. "
                  "Укажите его вручную: --tz 3 (или --tz Europe/Moscow).")
            sys.exit(2)
        print(f"Часовой пояс signal_time: UTC{off:+d}")
        return lambda text: naive_ms(text) - off * HOUR
    if tz_arg == "local":
        return lambda text: int(datetime.strptime(text, TS_FMT).timestamp() * 1000)
    try:
        off = float(tz_arg)
        return lambda text: naive_ms(text) - int(off * HOUR)
    except ValueError:
        from zoneinfo import ZoneInfo
        zi = ZoneInfo(tz_arg)
        return lambda text: int(
            datetime.strptime(text, TS_FMT).replace(tzinfo=zi).timestamp() * 1000)


# ----------------------------------------------------------------------------
# Движок симуляции
# ----------------------------------------------------------------------------

def simulate(side, entry, sl, tp, op, hi, lo, cl, *,
             be_trigger=None, max_n=None, ambiguous="sl"):
    """
    Идём по свечам после входа.
      be_trigger - цена, при достижении которой стоп переносится на entry
                   (действует со СЛЕДУЮЩЕЙ свечи - порядок внутри свечи неизвестен).
      max_n      - максимум свечей в сделке (тайм-стоп, выход по close).
    Возвращает (kind, exit_price, index, was_ambiguous),
    kind: TP / SL / BE / TIME / OPEN (OPEN - не закрылась за горизонт, выход по close).
    """
    long = side == "LONG"
    cur_sl = sl
    moved = False
    n = len(hi)
    for i in range(n):
        if long:
            sl_hit = lo[i] <= cur_sl
            tp_hit = hi[i] >= tp
        else:
            sl_hit = hi[i] >= cur_sl
            tp_hit = lo[i] <= tp

        if sl_hit and tp_hit:
            amb = True
            if ambiguous == "tp":
                return "TP", tp, i, amb
            sl_hit, tp_hit = True, False
        else:
            amb = False

        if sl_hit:
            # гэп через стоп: исполнение по open свечи, если он хуже стопа
            px = min(cur_sl, op[i]) if long else max(cur_sl, op[i])
            return ("BE" if moved else "SL"), px, i, amb
        if tp_hit:
            return "TP", tp, i, amb

        if be_trigger is not None and not moved:
            if (long and hi[i] >= be_trigger) or (not long and lo[i] <= be_trigger):
                moved = True
                cur_sl = entry

        if max_n is not None and i + 1 >= max_n:
            return "TIME", cl[i], i, False
    return "OPEN", cl[-1], n - 1, False


def excursions(side, entry, risk, hi, lo, upto):
    if side == "LONG":
        mfe = (max(hi[:upto + 1]) - entry) / risk
        mae = (entry - min(lo[:upto + 1])) / risk
    else:
        mfe = (entry - min(lo[:upto + 1])) / risk
        mae = (max(hi[:upto + 1]) - entry) / risk
    return max(mfe, 0.0), max(mae, 0.0)


def atr15(T, H, L, C, t0, n=14):
    """ATR(14) по закрытым 15m-свечам, собранным из 1m, до момента t0."""
    bar = 15 * MIN
    cut = t0 // bar * bar
    ja = bisect.bisect_left(T, cut - (n + 3) * bar)
    jb = bisect.bisect_left(T, cut)
    buckets = {}
    for j in range(ja, jb):
        k = T[j] // bar
        b = buckets.get(k)
        if b is None:
            buckets[k] = [H[j], L[j], C[j], 1, T[j]]
        else:
            b[0] = max(b[0], H[j])
            b[1] = min(b[1], L[j])
            if T[j] >= b[4]:
                b[2], b[4] = C[j], T[j]
            b[3] += 1
    keys = sorted(k for k, b in buckets.items() if b[3] >= 10)
    if len(keys) < n + 1:
        return None
    keys = keys[-(n + 1):]
    trs = []
    for a, b in zip(keys, keys[1:]):
        pc = buckets[a][2]
        h, l = buckets[b][0], buckets[b][1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / n


# ----------------------------------------------------------------------------
# Варианты
# ----------------------------------------------------------------------------

def make_variants():
    v = [("baseline (как в боте)", {})]
    for f in (0.9, 0.8, 0.7, 0.6):
        v.append((f"TP на {int(f * 100)}% пути", {"tp_frac": f}))
    for b in (0.5, 1.0):
        v.append((f"безубыток после +{b}R", {"be": b}))
    v.append(("TP 80% + безубыток +1R", {"tp_frac": 0.8, "be": 1.0}))
    for m in (0.25, 0.5, 1.0):
        v.append((f"SL = экстремум -/+ {m} ATR", {"atr_sl": m}))
    for h in (6, 12, 24):
        v.append((f"тайм-стоп {h} ч", {"max_h": h}))
    return v


def run_variant(side, entry, sl0, tp0, extreme, atr, v, data, policy, cost_pct):
    op, hi, lo, cl = data
    long = side == "LONG"
    sl, tp = sl0, tp0
    if "tp_frac" in v:
        tp = entry + (tp0 - entry) * v["tp_frac"]
    if "atr_sl" in v:
        if atr is None:
            return None
        sl = extreme - v["atr_sl"] * \
            atr if long else extreme + v["atr_sl"] * atr
    if (long and sl >= entry) or (not long and sl <= entry):
        return None
    risk = abs(entry - sl)
    be_trigger = None
    if "be" in v:
        be_trigger = entry + v["be"] * risk if long else entry - v["be"] * risk
    max_n = int(v["max_h"] * 60) if "max_h" in v else None

    kind, px, idx, amb = simulate(
        side, entry, sl, tp, op, hi, lo, cl,
        be_trigger=be_trigger, max_n=max_n, ambiguous=policy)
    pnl = (px - entry) if long else (entry - px)
    gross_r = pnl / risk
    risk_pct = risk / entry * 100
    net_r = gross_r - cost_pct / risk_pct
    return {"kind": kind, "gross_r": gross_r, "net_r": net_r,
            "idx": idx, "amb": amb, "risk": risk}


# ----------------------------------------------------------------------------
# Обработка сигналов
# ----------------------------------------------------------------------------

def load_signals(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for i, s in enumerate(raw):
        if s.get("result") not in ("TP", "SL"):
            continue
        if s.get("signal") not in ("LONG", "SHORT"):
            continue
        s = dict(s)
        s["idx"] = i
        out.append(s)
    return out


def get_segments(fetcher, symbol, sigs, horizon_ms):
    ivs = sorted([s["t0"] - PAD_LEFT, s["t0"] + horizon_ms] for s in sigs)
    merged = []
    for a, b in ivs:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    segs = []
    for a, b in merged:
        rows = fetcher.klines(symbol, a // MIN * MIN, (b // MIN + 1) * MIN)
        segs.append({
            "a": a, "b": b,
            "T": [r[0] for r in rows], "O": [r[1] for r in rows],
            "H": [r[2] for r in rows], "L": [r[3] for r in rows],
            "C": [r[4] for r in rows],
        })
    return segs


def analyze_signal(s, segs, args, variants, sl_buffer):
    t0 = s["t0"]
    horizon_ms = int(args.horizon * HOUR)
    seg = next((g for g in segs
                if g["a"] <= t0 - PAD_LEFT and g["b"] >= t0 + horizon_ms), None)
    if seg is None or not seg["T"]:
        return None, "нет данных"
    T, O, H, L, C = seg["T"], seg["O"], seg["H"], seg["L"], seg["C"]

    first_open = (t0 // MIN + 1) * MIN
    i0 = bisect.bisect_left(T, first_open)
    i1 = bisect.bisect_right(T, t0 + horizon_ms)
    if i1 - i0 < 5:
        return None, "нет данных"
    if T[i0] - first_open > 10 * MIN:
        return None, "пропуск в данных"

    op, hi, lo, cl = O[i0:i1], H[i0:i1], L[i0:i1], C[i0:i1]
    side = s["signal"]
    entry, sl0, tp0 = s["entry_price"], s["stop_loss"], s["take_profit"]
    long = side == "LONG"
    extreme = sl0 / (1 - sl_buffer) if long else sl0 / (1 + sl_buffer)
    atr = atr15(T, H, L, C, t0)

    # уровни должны быть упорядочены; бот округляет цены до 5 знаков, и у
    # дешёвых монет (например VTHOUSDT) SL может совпасть с entry
    if (long and not (sl0 < entry < tp0)) or (not long and not (tp0 < entry < sl0)):
        return None, "некорректные уровни (округление цен)"
    risk0 = abs(entry - sl0)
    rr = abs(tp0 - entry) / risk0
    risk_pct = risk0 / entry * 100
    cost_pct = args.fee + 2 * args.slip

    # проверка соответствия entry цене рынка
    j = bisect.bisect_right(T, t0) - 1
    entry_dev = abs(C[j] - entry) / entry * 100 if j >= 0 else None

    rec = {
        "idx": s["idx"], "t0": t0, "time": s["signal_time"],
        "symbol": s["symbol"], "side": side, "tracker": s["result"],
        "entry": entry, "sl": sl0, "tp": tp0, "rr": rr, "risk_pct": risk_pct,
        "atr_pct": (atr / entry * 100) if atr else None,
        "risk_atr": (risk0 / atr) if atr else None,
        "entry_dev": entry_dev, "vars": {},
    }
    data = (op, hi, lo, cl)
    for name, v in variants:
        res = run_variant(side, entry, sl0, tp0, extreme, atr, v, data,
                          args.ambiguous, cost_pct)
        if res is not None:
            rec["vars"][name] = res

    base_name = variants[0][0]
    base = rec["vars"][base_name]
    opt = run_variant(side, entry, sl0, tp0, extreme,
                      atr, {}, data, "tp", cost_pct)
    rec["base_kind"] = base["kind"]
    rec["base_opt_kind"] = opt["kind"]
    rec["base_opt_net_r"] = opt["net_r"]
    rec["amb"] = base["amb"]
    rec["duration_min"] = (base["idx"] + 1)
    mfe, mae = excursions(side, entry, risk0, hi, lo, base["idx"])
    rec["mfe_r"], rec["mae_r"] = mfe, mae
    rec["mfe_path"] = mfe / rr
    return rec, None


# ----------------------------------------------------------------------------
# Отчёт
# ----------------------------------------------------------------------------

def summarize(vals):
    n = len(vals)
    if n == 0:
        return 0, 0.0, 0.0, 0.0
    tot = sum(vals)
    avg = tot / n
    se = pstdev(vals) / math.sqrt(n) if n > 1 else 0.0
    return n, tot, avg, se


def pct(a, b):
    return f"{a / b * 100:5.1f}%" if b else "   n/a"


def build_report(recs, variants, args, skipped):
    out = []
    P = out.append
    n = len(recs)
    t_med = median(r["t0"] for r in recs)

    P("=" * 78)
    P(f"REPLAY: сигналов обработано {n}  (пропущено: {dict(skipped) or 0})")
    P(f"Горизонт {args.horizon} ч | комиссия {args.fee}% за круг | "
      f"проскальзывание {args.slip}% на сторону | неоднозначная свеча -> {args.ambiguous.upper()}")
    devs = [r["entry_dev"] for r in recs if r["entry_dev"] is not None]
    if devs:
        P(f"Проверка данных: медианное отклонение entry от цены 1m-свечи "
          f"{median(devs):.3f}% (должно быть малым)")
    P("=" * 78)

    # --- 1. Сверка с tracker
    P("\n1) СВЕРКА С TRACKER (результат по high/low свечей vs запись в signals.json)")
    mat = defaultdict(int)
    for r in recs:
        mat[(r["tracker"], r["base_kind"])] += 1
    P(f"   {'tracker':8s} {'replay TP':>10s} {'replay SL':>10s} {'replay OPEN':>12s}")
    for trk in ("TP", "SL"):
        P(f"   {trk:8s} {mat[(trk, 'TP')]:10d} {mat[(trk, 'SL')]:10d} {mat[('' + trk, 'OPEN')]:12d}")
    agree = sum(mat[(k, k)] for k in ("TP", "SL"))
    P(f"   Совпадение: {pct(agree, n)}")
    amb = sum(1 for r in recs if r["amb"])
    P(f"   Неоднозначных свечей (в одной минуте задеты и SL, и TP): {amb} ({pct(amb, n).strip()})")

    # --- 2. baseline
    P("\n2) BASELINE ПО СВЕЧАМ (то, что бот давал бы на самом деле)")
    gross = [r["vars"][variants[0][0]]["gross_r"] for r in recs]
    net = [r["vars"][variants[0][0]]["net_r"] for r in recs]
    net_opt = [r["base_opt_net_r"] for r in recs]
    for label, vals in (("до комиссий", gross), ("после комиссий (SL при неоднозначности)", net),
                        ("после комиссий (TP при неоднозначности)", net_opt)):
        k, tot, avg, se = summarize(vals)
        P(f"   {label:44s} avgR {avg:+.3f} +-{se:.3f}   sumR {tot:+8.1f}")
    trk_r = [(r["rr"] if r["tracker"] == "TP" else -1.0) for r in recs]
    k, tot, avg, se = summarize(trk_r)
    P(f"   {'по записи tracker.py (для сравнения)':44s} avgR {avg:+.3f} +-{se:.3f}   sumR {tot:+8.1f}")

    # --- 3. MAE/MFE
    P("\n3) MAE / MFE (в долях исходного риска R; путь к TP = 1.0)")
    sl_tr = [r for r in recs if r["base_kind"] == "SL"]
    tp_tr = [r for r in recs if r["base_kind"] == "TP"]
    P(f"   Сделки, закрытые по SL: {len(sl_tr)}. Дошли до доли пути к TP до стопа:")
    for th in (0.5, 0.7, 0.8, 0.9):
        c = sum(1 for r in sl_tr if r["mfe_path"] >= th)
        P(f"      >= {int(th * 100):3d}% пути: {c:4d}  ({pct(c, len(sl_tr)).strip()})")
    P("   Из них прошли в плюс по R до стопа:")
    for th in (0.5, 1.0, 1.5):
        c = sum(1 for r in sl_tr if r["mfe_r"] >= th)
        P(f"      MFE >= +{th}R: {c:4d}  ({pct(c, len(sl_tr)).strip()})")
    P(f"   Сделки, закрытые по TP: {len(tp_tr)}. Как глубоко уходили против входа:")
    for th in (0.5, 0.8, 0.9):
        c = sum(1 for r in tp_tr if r["mae_r"] >= th)
        P(f"      MAE >= {th}R: {c:4d}  ({pct(c, len(tp_tr)).strip()})")

    # --- 4. варианты
    P("\n4) ВАРИАНТЫ УПРАВЛЕНИЯ (R считается в единицах риска самого варианта, после комиссий)")
    P(f"   {'вариант':32s} {'n':>4s} {'TP/SL/BE/TIME/OPEN':>20s} {'в плюс':>7s} "
      f"{'avgR':>7s} {'+-SE':>6s} {'sumR':>8s} {'H1':>7s} {'H2':>7s}")
    for name, _ in variants:
        rs = [(r["t0"], r["vars"][name]) for r in recs if name in r["vars"]]
        if not rs:
            continue
        vals = [x["net_r"] for _, x in rs]
        k, tot, avg, se = summarize(vals)
        cnt = defaultdict(int)
        for _, x in rs:
            cnt[x["kind"]] += 1
        kinds = "/".join(str(cnt[q])
                         for q in ("TP", "SL", "BE", "TIME", "OPEN"))
        win = sum(1 for x in vals if x > 0)
        h1 = [x["net_r"] for t, x in rs if t <= t_med]
        h2 = [x["net_r"] for t, x in rs if t > t_med]
        a1 = f"{sum(h1) / len(h1):+.3f}" if h1 else "  n/a"
        a2 = f"{sum(h2) / len(h2):+.3f}" if h2 else "  n/a"
        P(f"   {name:32s} {k:4d} {kinds:>20s} {pct(win, k):>7s} "
          f"{avg:+7.3f} {se:6.3f} {tot:+8.1f} {a1:>7s} {a2:>7s}")
    P("   H1/H2 - средний R в первой/второй половине периода (устойчивость).")
    P("   Для ATR-вариантов n меньше, если не хватило данных для ATR.")

    # --- 5. фильтры на baseline
    P("\n5) ФИЛЬТРЫ НА BASELINE (после комиссий)")
    base = variants[0][0]

    def table(title, key, edges, fmt):
        P(f"   {title}")
        P(f"      {'диапазон':16s} {'n':>5s} {'в плюс':>7s} {'avgR':>7s} {'+-SE':>6s} {'sumR':>8s}")
        for lo_, hi_ in zip(edges[:-1], edges[1:]):
            vals = [r["vars"][base]["net_r"] for r in recs
                    if r[key] is not None and lo_ <= r[key] < hi_]
            if not vals:
                continue
            k, tot, avg, se = summarize(vals)
            win = sum(1 for x in vals if x > 0)
            lab = f"{fmt(lo_)}-{fmt(hi_)}"
            P(f"      {lab:16s} {k:5d} {pct(win, k):>7s} {avg:+7.3f} {se:6.3f} {tot:+8.1f}")

    INF = 1e9
    table("по risk_percent (расстояние до SL, % от входа):", "risk_pct",
          [0, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, INF], lambda x: "inf" if x >= INF else f"{x:g}")
    table("по risk/reward:", "rr", [0, 1.5, 2.0, 2.5, 3.0, INF],
          lambda x: "inf" if x >= INF else f"{x:g}")
    atr_vals = sorted(r["risk_atr"] for r in recs if r["risk_atr"] is not None)
    if len(atr_vals) >= 40:
        q = [0] + [atr_vals[int(len(atr_vals) * p)]
                   for p in (0.25, 0.5, 0.75)] + [INF]
        table("по риску в ATR(15m) (SL-расстояние / ATR), квартили:", "risk_atr", q,
              lambda x: "inf" if x >= INF else f"{x:.2f}")

    P("\n   Комбинированные фильтры (baseline):")
    P(f"      {'фильтр':36s} {'n':>5s} {'avgR':>7s} {'+-SE':>6s} {'sumR':>8s} {'H1':>7s} {'H2':>7s}")
    combos = [
        ("risk% <= 1.5", lambda r: r["risk_pct"] <= 1.5),
        ("RR >= 2", lambda r: r["rr"] >= 2),
        ("risk% <= 1.5 и RR >= 2",
         lambda r: r["risk_pct"] <= 1.5 and r["rr"] >= 2),
    ]
    if atr_vals:
        med_atr = atr_vals[len(atr_vals) // 2]
        combos.append((f"риск <= {med_atr:.2f} ATR (медиана)",
                       lambda r: r["risk_atr"] is not None and r["risk_atr"] <= med_atr))
    for label, fn in combos:
        sel = [r for r in recs if fn(r)]
        vals = [r["vars"][base]["net_r"] for r in sel]
        if not vals:
            continue
        k, tot, avg, se = summarize(vals)
        h1 = [r["vars"][base]["net_r"] for r in sel if r["t0"] <= t_med]
        h2 = [r["vars"][base]["net_r"] for r in sel if r["t0"] > t_med]
        a1 = f"{sum(h1) / len(h1):+.3f}" if h1 else "  n/a"
        a2 = f"{sum(h2) / len(h2):+.3f}" if h2 else "  n/a"
        P(f"      {label:36s} {k:5d} {avg:+7.3f} {se:6.3f} {tot:+8.1f} {a1:>7s} {a2:>7s}")

    P("\nКАК ЧИТАТЬ: ориентируйтесь на варианты, где avgR выше baseline заметно больше, "
      "чем +-SE,")
    P("и где H1 и H2 одного знака. Всё, что подобрано на этих же данных, на новых "
      "будет хуже.")
    P("Это анализ истории, а не финансовая рекомендация.")
    return "\n".join(out)


def write_csv(recs, path):
    cols = ["idx", "time", "symbol", "side", "tracker", "base_kind",
            "base_opt_kind", "amb", "duration_min", "entry", "sl", "tp", "rr",
            "risk_pct", "atr_pct", "risk_atr", "mfe_r", "mae_r", "mfe_path",
            "entry_dev"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in recs:
            w.writerow([round(r[c], 5) if isinstance(r[c], float) else r[c]
                        for c in cols])


# ----------------------------------------------------------------------------
# Основной прогон
# ----------------------------------------------------------------------------

def run(sigs, fetcher, args, tz_conv):
    for s in sigs:
        s["t0"] = tz_conv(s["signal_time"])
    variants = make_variants()
    by_symbol = defaultdict(list)
    for s in sigs:
        by_symbol[s["symbol"]].append(s)

    recs, skipped = [], defaultdict(int)
    horizon_ms = int(args.horizon * HOUR)
    total = len(by_symbol)
    for n_sym, (symbol, group) in enumerate(sorted(by_symbol.items()), 1):
        print(f"[{n_sym}/{total}] {symbol}: сигналов {len(group)}", flush=True)
        try:
            segs = get_segments(fetcher, symbol, group, horizon_ms)
        except SymbolError:
            skipped["символ недоступен"] += len(group)
            continue
        for s in group:
            rec, why = analyze_signal(s, segs, args, variants, args.sl_buffer)
            if rec is None:
                skipped[why] += 1
            else:
                recs.append(rec)
    return recs, variants, skipped


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Перепроигрыш сигналов по 1m-свечам")
    p.add_argument("--signals", default="signals.json")
    p.add_argument("--tz", default="auto",
                   help="auto | local | число часов (3) | IANA-имя (Europe/Moscow)")
    p.add_argument("--horizon", type=float, default=72.0,
                   help="сколько часов держать сделку максимум (по умолчанию 72)")
    p.add_argument("--fee", type=float, default=0.08,
                   help="комиссия за круг, %% (по умолчанию 0.08)")
    p.add_argument("--slip", type=float, default=0.0,
                   help="проскальзывание на сторону, %% (по умолчанию 0)")
    p.add_argument("--ambiguous", choices=["sl", "tp"], default="sl",
                   help="что считать, если в одной свече задеты SL и TP")
    p.add_argument("--sl-buffer", type=float, default=0.005,
                   help="буфер SL за экстремумом в market.py (0.005 = 0.5%%)")
    p.add_argument("--limit", type=int, default=0,
                   help="взять только N первых сигналов")
    p.add_argument("--cache", default="kline_cache")
    p.add_argument("--out", default="replay_out")
    p.add_argument("--pause", type=float, default=0.12,
                   help="пауза между запросами, с")
    return p.parse_args(argv)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = parse_args()
    sigs = load_signals(args.signals)
    if args.limit:
        sigs = sigs[:args.limit]
    if not sigs:
        print("Нет закрытых сигналов (TP/SL) в файле.")
        return
    print(f"Сигналов к обработке: {len(sigs)}")
    fetcher = Fetcher(args.cache, args.pause)
    tz_conv = make_tz_converter(args.tz, sigs, fetcher)
    recs, variants, skipped = run(sigs, fetcher, args, tz_conv)
    if not recs:
        print("Не удалось обработать ни одного сигнала:", dict(skipped))
        return
    os.makedirs(args.out, exist_ok=True)
    report = build_report(recs, variants, args, skipped)
    print("\n" + report)
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report)
    write_csv(recs, os.path.join(args.out, "replay_results.csv"))
    print(f"\nГотово: {args.out}/report.txt и {args.out}/replay_results.csv")


if __name__ == "__main__":
    main()
