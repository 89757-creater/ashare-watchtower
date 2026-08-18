# -*- coding: utf-8 -*-
"""ETF 动量榜每日刷新：抓取腾讯行情日 K，计算动量/量能/节奏标签 + 低买高卖波段信号，输出 artifact。

波段信号口径（透明规则，非预测承诺）：
- pos20：现价在最近 20 日收盘价区间中的位置（0=区间最低，100=区间最高）
- 低吸窗口：pos20 <= 30 且近5日已止跌回升（ret5 > 0）
- 低位磨底：pos20 <= 30 但 ret5 <= 0（低位未企稳，不急接）
- 高抛窗口：pos20 >= 75 且 ret5 > 0（区间高位仍上冲，分批兑现）
- 高位回落：pos20 >= 75 且 ret5 <= 0
- 其余：中段观望
- 参考低吸价 = 20 日最低收盘，参考高抛价 = 20 日最高收盘
"""
import json
import sys
import time
import urllib.request

# ===================== 用户配置区：观察池（交易所前缀, 代码, 名称, 是否持仓） =====================
ETFS = [
    ("sh588170", "588170", "科创半导体ETF", True),
    ("sh562590", "562590", "半导体设备ETF", False),
    ("sz159995", "159995", "芯片ETF", False),
    ("sh512480", "512480", "半导体ETF", False),
    ("sh588000", "588000", "科创50ETF", False),
    ("sh512880", "512880", "证券ETF", False),
    ("sh512660", "512660", "军工ETF", False),
    ("sh515790", "515790", "光伏ETF", False),
    ("sh512010", "512010", "医药ETF", False),
    ("sh512170", "512170", "医疗ETF", False),
    ("sz159928", "159928", "消费ETF", False),
    ("sh512690", "512690", "酒ETF", False),
    ("sh515050", "515050", "通信ETF", False),
    ("sz159819", "159819", "人工智能ETF", False),
    ("sh512400", "512400", "有色金属ETF", False),
    ("sh518880", "518880", "黄金ETF", False),
    ("sh512800", "512800", "银行ETF", False),
    ("sh512000", "512000", "券商ETF", False),
    ("sh513130", "513130", "恒生科技ETF", False),
    ("sh513050", "513050", "中概互联网ETF", False),
    ("sh562500", "562500", "机器人ETF", False),
]
INDICES = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
]

# 波段信号阈值（可按偏好调整）
LOW_POS = 30    # 区间位置 <= 30% 视为低位区
HIGH_POS = 75   # 区间位置 >= 75% 视为高位区
# ==============================================================================

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch_kline(symbol, count=30, fq=True):
    fq_part = ",qfq" if fq else ""
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param="
           + symbol + ",day,,," + str(count) + fq_part)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    node = payload.get("data", {}).get(symbol, {})
    rows = node.get("qfqday") or node.get("day") or []
    out = []
    for r in rows:
        try:
            out.append((str(r[0]), float(r[2]), float(r[5])))  # date, close, volume
        except (IndexError, TypeError, ValueError):
            continue
    return out


def metrics(k):
    closes = [c for _, c, _ in k]
    vols = [v for _, _, v in k]
    n = len(closes)
    if n < 6:
        return None
    last, prev = closes[-1], closes[-2]
    pct = (last / prev - 1) * 100 if prev else None
    ret5 = (last / closes[-6] - 1) * 100
    ret20 = (last / closes[-21] - 1) * 100 if n >= 21 else None
    v5 = sum(vols[-5:]) / 5
    v20 = sum(vols[-25:-5]) / max(1, min(20, n - 5)) if n > 5 else 0
    vol_ratio = (v5 / v20) if v20 else None
    win = closes[-20:]
    low20, high20 = min(win), max(win)
    dd20 = (last / high20 - 1) * 100
    span = high20 - low20
    pos20 = (last - low20) / span * 100 if span > 0 else 50.0
    return dict(close=last, pct=pct, ret5=ret5, ret20=ret20,
                vol_ratio=vol_ratio, dd20=dd20, date=k[-1][0],
                low20=low20, high20=high20, pos20=pos20)


def make_tag(ret5, ret20, vol_ratio, dd20):
    if ret5 is None:
        return "数据不足"
    if ret5 > 0 and ret20 is not None and ret20 > 0:
        if (vol_ratio or 0) >= 1.3 and (dd20 or -99) >= -2:
            return "放量突破"
        return "趋势向上"
    if ret5 >= 5 and (ret20 or 0) < 0:
        return "超跌反弹"
    if ret5 > 0:
        return "企稳回升"
    return "弱势整理"


def make_signal(pos20, ret5):
    """低买高卖波段信号：区间位置 × 动量方向。"""
    if pos20 is None or ret5 is None:
        return "数据不足"
    if pos20 <= LOW_POS:
        return "低吸窗口" if ret5 > 0 else "低位磨底"
    if pos20 >= HIGH_POS:
        return "高抛窗口" if ret5 > 0 else "高位回落"
    return "中段观望"


def run(ctx):
    etfs, market, failed = [], [], []
    last_date = ""

    for symbol, code, name, holding in ETFS:
        try:
            k = fetch_kline(symbol)
            m = metrics(k)
            if not m:
                failed.append(code)
                continue
            last_date = max(last_date, m.pop("date"))
            etfs.append(dict(code=code, name=name, holding=holding,
                             close=round(m["close"], 4),
                             pct=round(m["pct"], 2) if m["pct"] is not None else None,
                             ret5=round(m["ret5"], 2),
                             ret20=round(m["ret20"], 2) if m["ret20"] is not None else None,
                             vol_ratio=round(m["vol_ratio"], 2) if m["vol_ratio"] else None,
                             dd20=round(m["dd20"], 2),
                             low20=round(m["low20"], 4),
                             high20=round(m["high20"], 4),
                             pos20=round(m["pos20"], 1),
                             signal=make_signal(m["pos20"], m["ret5"]),
                             tag=make_tag(m["ret5"], m["ret20"], m["vol_ratio"], m["dd20"])))
        except Exception:
            failed.append(code)
        time.sleep(0.15)

    for symbol, name in INDICES:
        try:
            k = fetch_kline(symbol)
            m = metrics(k)
            if m:
                market.append(dict(code=symbol, name=name, close=round(m["close"], 2),
                                   pct=round(m["pct"] or 0, 2), ret5=round(m["ret5"], 2),
                                   ret20=round(m["ret20"], 2) if m["ret20"] is not None else None))
        except Exception:
            pass
        time.sleep(0.15)

    etfs.sort(key=lambda e: (e["ret5"] if e["ret5"] is not None else -999), reverse=True)

    # 低吸潜力榜：区间位置最低的「低吸窗口」标的优先，其次「低位磨底」
    def pick_rank(e):
        order = {"低吸窗口": 0, "低位磨底": 1}
        return (order.get(e["signal"], 9), e["pos20"] if e["pos20"] is not None else 999)

    picks = []
    for e in sorted([x for x in etfs if x["signal"] in ("低吸窗口", "低位磨底")], key=pick_rank)[:3]:
        picks.append({
            "code": e["code"], "name": e["name"], "close": e["close"],
            "pos20": e["pos20"], "signal": e["signal"],
            "low20": e["low20"], "high20": e["high20"], "holding": e["holding"],
            "reason": "20日区间位置 %.0f%%%s；参考低吸 %.3f / 高抛 %.3f" % (
                e["pos20"], "，近5日止跌回升" if e["signal"] == "低吸窗口" else "，尚未企稳",
                e["low20"], e["high20"]),
        })

    note = ""
    if failed:
        note = "以下标的本次取数失败已跳过：" + "、".join(failed)

    artifact = {
        "as_of": (last_date + " 收盘") if last_date else "数据暂缺",
        "market": market,
        "etfs": etfs,
        "picks": picks,
        "note": note,
    }
    return {"artifact": artifact}
