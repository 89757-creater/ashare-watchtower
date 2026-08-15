# -*- coding: utf-8 -*-
"""Fetch latest quote for 588170.SH, compute position P&L and daily price-limit state.

Runs every 30 min during trading hours. Remembers the first limit-up / limit-down
touch time of the day in a state file inside the automation workspace.
"""
import json
import os
import urllib.request

# ===================== 用户配置区（安装时按持仓修改） =====================
SHARES = 600        # 持仓份额
COST = 1.059        # 持仓成本价
STOP_LOSS = 0.85    # 止损价
TAKE_PROFIT = 1.05  # 止盈价
LIMIT_RATIO = 0.20  # 日涨跌停幅度：主板 0.10 / 创业板·科创板 0.20 / ST 0.05

QUOTE_URL = "https://qt.gtimg.cn/q=sh588170"  # 替换 sh588170 为你的标的（sh/sz + 代码）
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
        return (
            f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}",
            f"{raw[8:10]}:{raw[10:12]}",
        )
    from datetime import datetime

    now = datetime.now()
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M")


def state_path():
    base = os.environ.get("DAIMON_BLUEPRINT_AUTOMATION_WORKSPACE_PATH") or os.path.dirname(
        os.path.abspath(__file__)
    )
    return os.path.join(base, "limit_state.json")


def load_state():
    try:
        with open(state_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def run(ctx):
    q = fetch_quote()
    date, time_str = parse_time(q["raw_time"])

    price = q["price"]
    limit_up = round(q["preclose"] * (1 + LIMIT_RATIO), 3)
    limit_down = round(q["preclose"] * (1 - LIMIT_RATIO), 3)

    # Track first touch of limit prices during the day
    state = load_state()
    if state.get("date") != date:
        state = {"date": date, "hit_up_time": "", "hit_down_time": ""}
    if q["high"] >= limit_up and not state.get("hit_up_time"):
        state["hit_up_time"] = time_str
    if q["low"] <= limit_down and not state.get("hit_down_time"):
        state["hit_down_time"] = time_str
    save_state(state)

    if state.get("hit_up_time"):
        limit_state, limit_time = "hit_up", state["hit_up_time"]
    elif state.get("hit_down_time"):
        limit_state, limit_time = "hit_down", state["hit_down_time"]
    else:
        limit_state, limit_time = "none", ""

    market_value = round(price * SHARES, 2)
    float_pnl = round(market_value - COST * SHARES, 2)
    float_pnl_pct = round((price / COST - 1) * 100, 2)

    if q["low"] <= STOP_LOSS or price <= STOP_LOSS:
        alert = "stop_loss"
        note = "已触及止损线 0.85，按纪律执行止损，不要犹豫。"
    elif q["high"] >= TAKE_PROFIT or price >= TAKE_PROFIT:
        alert = "take_profit"
        note = "已触及止盈区 1.05（成本区），建议按计划在反弹中分批减仓。"
    elif price <= STOP_LOSS + 0.03:
        alert = "near_stop"
        note = "价格逼近止损线 0.85，跌破即离场；反弹至 1.05 附近为减仓窗口。"
    elif price >= TAKE_PROFIT - 0.03:
        alert = "near_target"
        note = "价格逼近止盈区 1.05，接近成本区，准备分批减仓。"
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
            "market_value": market_value,
            "float_pnl": float_pnl,
            "float_pnl_pct": float_pnl_pct,
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
