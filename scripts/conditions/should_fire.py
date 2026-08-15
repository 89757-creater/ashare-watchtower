# -*- coding: utf-8 -*-
"""Condition for the 588170 key-level alert automation.

Evaluated every 30 minutes. Returns True only during trading hours when a
NEW key-level event appears today (first touch of limit-up / limit-down /
stop-loss / take-profit). Already-reported events are remembered in a state
file under the task directory, so each event triggers at most one run per day.
"""
import json
import os
import urllib.request
from datetime import datetime

# ===================== 用户配置区（与 sentinel_quote.py 保持一致） =====================
STOP_LOSS = 0.85
TAKE_PROFIT = 1.05
LIMIT_RATIO = 0.20
QUOTE_URL = "https://qt.gtimg.cn/q=sh588170"
# =======================================================================


def _fetch():
    req = urllib.request.Request(
        QUOTE_URL,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        text = resp.read().decode("gbk", errors="replace")
    payload = text.split("=", 1)[1].strip().strip(";").strip('"')
    p = payload.split("~")
    return {
        "price": float(p[3]),
        "preclose": float(p[4]),
        "high": float(p[33]),
        "low": float(p[34]),
    }


def _state_file(ctx):
    task_dir = ctx.get("taskDir") or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(task_dir, "alert_state.json")


def should_fire(ctx):
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    hhmm = now.strftime("%H:%M")
    if not ("09:30" <= hhmm <= "15:10"):
        return False

    try:
        q = _fetch()
    except Exception:
        return False

    limit_up = round(q["preclose"] * (1 + LIMIT_RATIO), 3)
    limit_down = round(q["preclose"] * (1 - LIMIT_RATIO), 3)

    events = []
    if q["high"] >= limit_up:
        events.append("hit_up")
    if q["low"] <= limit_down:
        events.append("hit_down")
    if q["low"] <= STOP_LOSS:
        events.append("stop_loss")
    if q["high"] >= TAKE_PROFIT:
        events.append("take_profit")
    if not events:
        return False

    path = _state_file(ctx)
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}

    today = now.strftime("%Y-%m-%d")
    fired = state.get("events", []) if state.get("date") == today else []
    new_events = [e for e in events if e not in fired]
    if not new_events:
        return False

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": today, "events": sorted(set(fired) | set(events))}, f)
    except Exception:
        pass
    return True
