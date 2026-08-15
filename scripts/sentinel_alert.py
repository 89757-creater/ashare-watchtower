# -*- coding: utf-8 -*-
"""Business run for the 588170 key-level alert automation.

Fires only when the condition detects a fresh limit-up/down touch or a
stop-loss / take-profit cross. Recomputes the full artifact so the bound
Widget shows the latest state, and the notification delivery pushes an alert.
"""
import json
import os
import urllib.request
from datetime import datetime

# ===================== 用户配置区（与 sentinel_quote.py 保持一致） =====================
SHARES = 600
COST = 1.059
STOP_LOSS = 0.85
TAKE_PROFIT = 1.05
LIMIT_RATIO = 0.20

QUOTE_URL = "https://qt.gtimg.cn/q=sh588170"
# =======================================================================


def fetch_quote():
    req = urllib.request.Request(
        QUOTE_URL,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        text = resp.read().decode("gbk", errors="replace")
    payload = text.split("=", 1)[1].strip().strip(";").strip('"')
    p = payload.split("~")
    return {
        "price": float(p[3]),
        "preclose": float(p[4]),
        "high": float(p[33]),
        "low": float(p[34]),
        "pct": float(p[32]),
        "raw_time": p[30] if len(p) > 30 else "",
    }


def parse_time(raw):
    if len(raw) >= 12 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}", f"{raw[8:10]}:{raw[10:12]}"
    now = datetime.now()
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M")


def run(ctx):
    q = fetch_quote()
    date, time_str = parse_time(q["raw_time"])
    price = q["price"]
    limit_up = round(q["preclose"] * (1 + LIMIT_RATIO), 3)
    limit_down = round(q["preclose"] * (1 - LIMIT_RATIO), 3)

    if q["high"] >= limit_up:
        limit_state, limit_time = "hit_up", time_str
    elif q["low"] <= limit_down:
        limit_state, limit_time = "hit_down", time_str
    else:
        limit_state, limit_time = "none", ""

    if q["low"] <= STOP_LOSS or price <= STOP_LOSS:
        alert = "stop_loss"
        note = "已触及止损线 0.85，按纪律执行止损，不要犹豫。"
    elif q["high"] >= TAKE_PROFIT or price >= TAKE_PROFIT:
        alert = "take_profit"
        note = "已触及止盈区 1.05（成本区），建议按计划在反弹中分批减仓。"
    elif price <= STOP_LOSS + 0.03:
        alert = "near_stop"
        note = "价格逼近止损线 0.85，跌破即离场。"
    elif price >= TAKE_PROFIT - 0.03:
        alert = "near_target"
        note = "价格逼近止盈区 1.05，准备分批减仓。"
    else:
        alert = "none"
        note = "反弹至 1.05 附近为减仓窗口；跌破 0.85 执行止损。"

    return {
        "artifact": {
            "price": price,
            "change_pct": q["pct"],
            "date": date,
            "time": time_str,
            "shares": SHARES,
            "cost": COST,
            "market_value": round(price * SHARES, 2),
            "float_pnl": round(price * SHARES - COST * SHARES, 2),
            "float_pnl_pct": round((price / COST - 1) * 100, 2),
            "day_high": q["high"],
            "day_low": q["low"],
            "stop_loss": STOP_LOSS,
            "take_profit": TAKE_PROFIT,
            "alert": alert,
            "note": note,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "limit_state": limit_state,
            "limit_time": limit_time,
        }
    }
