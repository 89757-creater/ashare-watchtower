# -*- coding: utf-8 -*-
"""舆情雷达规则引擎：抓取新浪财经 7x24 电报，关键词规则映射板块/ETF 并做利多利空初判。"""
import json
import re
import time
import urllib.request
from datetime import datetime

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept": "application/json"}

# 板块规则：关键词 -> (板块名, [(ETF代码, ETF名)])
SECTOR_RULES = [
    (["半导体", "芯片", "光刻", "晶圆", "存储器", "集成电路", "中芯", "寒武纪", "算力芯片", "先进封装"],
     "半导体", [("588170", "科创半导体ETF"), ("562590", "半导体设备ETF"),
                ("159995", "芯片ETF"), ("512480", "半导体ETF"), ("588000", "科创50ETF")]),
    (["科创板", "科创50", "硬科技"], "科创板", [("588000", "科创50ETF")]),
    (["创新药", "医药", "医疗", "医保", "集采", "疫苗", "生物医药"],
     "医药医疗", [("512010", "医药ETF"), ("512170", "医疗ETF")]),
    (["券商", "证券", "IPO", "并购重组", "资本市场", "成交额", "两融"],
     "证券", [("512880", "证券ETF"), ("512000", "券商ETF")]),
    (["军工", "国防", "航母", "导弹", "战机", "兵器"], "军工", [("512660", "军工ETF")]),
    (["光伏", "硅片", "组件", "多晶硅", "装机"], "光伏", [("515790", "光伏ETF")]),
    (["白酒", "茅台", "五粮液", "酒类"], "白酒", [("512690", "酒ETF")]),
    (["消费", "零售", "食品饮料", "家电", "以旧换新"], "消费", [("159928", "消费ETF")]),
    (["5G", "6G", "通信", "光模块", "光通信", "基站"], "通信", [("515050", "通信ETF")]),
    (["人工智能", "大模型", "AI", "智能体", "算力", "数据中心"],
     "人工智能", [("159819", "人工智能ETF"), ("515050", "通信ETF")]),
    (["机器人", "人形机器人", "具身智能"], "机器人", [("562500", "机器人ETF")]),
    (["黄金", "金价", "避险", "贵金属"], "黄金", [("518880", "黄金ETF")]),
    (["铜", "铝", "稀土", "有色", "锂价", "锂矿", "钴"], "有色金属", [("512400", "有色金属ETF")]),
    (["银行", "LPR", "存款利率", "净息差"], "银行", [("512800", "银行ETF")]),
    (["恒生", "港股", "腾讯", "阿里巴巴", "美团", "中概"],
     "港股/中概", [("513130", "恒生科技ETF"), ("513050", "中概互联网ETF")]),
    (["降准", "降息", "央行", "流动性", "货币政策"],
     "宏观流动性", [("512800", "银行ETF"), ("512880", "证券ETF")]),
    (["关税", "制裁", "出口管制", "实体清单", "地缘", "冲突", "战争"],
     "地缘/贸易", [("518880", "黄金ETF"), ("512660", "军工ETF")]),
    (["原油", "油价", "OPEC", "天然气"], "能源", [("512400", "有色金属ETF")]),
]

POS_WORDS = ["利好", "获批", "中标", "涨停", "大涨", "增长", "超预期", "突破", "开工",
             "签约", "扩产", "涨价", "回购", "增持", "支持", "鼓励", "补贴", "创新高",
             "净流入", "降准", "降息", "放宽", "落地", "加快", "推进", "复苏", "回暖"]
NEG_WORDS = ["利空", "处罚", "立案", "暴雷", "违约", "下跌", "大跌", "低于预期", "减产",
             "降价", "减持", "制裁", "关税", "事故", "召回", "创新低", "净流出", "退市",
             "风险警示", "加息", "收紧", "叫停", "亏损", "延期", "否决", "冲突升级"]
MACRO_WORDS = ["央行", "国务院", "证监会", "财政部", "发改委", "政治局", "降准", "降息",
               "加息", "关税", "制裁", "战争", "地震", "财政部", "工信部", "政策"]
HOLDING_WORDS = ["半导体", "芯片", "光刻", "晶圆", "集成电路", "科创", "中芯", "存储"]


def fetch_sina(pages=2):
    items = []
    for page in range(1, pages + 1):
        url = ("https://zhibo.sina.com.cn/api/zhibo/feed?page=%d&page_size=20"
               "&zhibo_id=152&tag_id=0&dire=f&dpc=1&id=0&_=%d") % (page, int(time.time()))
        try:
            req = urllib.request.Request(url, headers=UA)
            data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
            items.extend(data.get("result", {}).get("data", {}).get("feed", {}).get("list", []))
        except Exception:
            break
        time.sleep(0.3)
    return items


def split_title(text):
    m = re.match(r"^【(.+?)】\s*(.*)$", text or "", re.S)
    if m:
        return m.group(1).strip(), re.sub(r"\s+", " ", m.group(2)).strip()
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[:20], clean


NOISE_WORDS = ["业绩说明会", "注册资本", "网上路演", "投资者关系活动", "股东大会通知",
               "接待机构调研", "停牌核查", "复牌公告"]


def analyze(text):
    hits, sectors, etfs = [], [], {}
    for kws, sector, pool in SECTOR_RULES:
        for kw in kws:
            if kw in text:
                hits.append(kw)
                if sector not in sectors:
                    sectors.append(sector)
                for code, name in pool:
                    etfs.setdefault(code, name)
                break  # 每条规则只记一次
    pos = sum(1 for w in POS_WORDS if w in text)
    neg = sum(1 for w in NEG_WORDS if w in text)
    macro = [w for w in MACRO_WORDS if w in text]
    if pos > neg:
        direction = "利多"
    elif neg > pos:
        direction = "利空"
    else:
        direction = "中性"
    if macro:
        impact = "高"
    elif sectors:
        impact = "中"
    else:
        impact = "低"
    return hits, sectors, etfs, direction, impact, macro, pos, neg


def run(ctx):
    raw = fetch_sina()
    now = datetime.now()
    events = []
    for it in raw:
        text = (it.get("rich_text") or "").strip()
        if not text or any(w in text for w in NOISE_WORDS):
            continue
        hits, sectors, etf_map, direction, impact, macro, pos, neg = analyze(text)
        if not sectors and not macro:
            continue  # 只保留有板块或宏观传导路径的事件
        title, summary = split_title(text)
        ts = str(it.get("create_time") or "")
        tstr = ts[11:16] if len(ts) >= 16 else ""
        holding_rel = any(w in text for w in HOLDING_WORDS)
        etf_list = []
        for code, name in list(etf_map.items())[:4]:
            entry = {"code": code, "name": name, "direction": direction}
            if code == "588170" and holding_rel:
                entry["holding"] = True
            etf_list.append(entry)
        kw_show = "、".join((hits + macro)[:4])
        score = {"高": 30, "中": 20, "低": 10}[impact] + (5 if direction != "中性" else 0) \
            + len(hits) + 2 * len(macro)
        events.append({
            "_score": score,
            "_ts": ts,
            "title": title[:20],
            "summary": summary[:120] if summary else title,
            "source": "新浪财经·7x24",
            "time": tstr,
            "heat": min(5, 2 + len(hits) + len(macro)),
            "direction": direction,
            "impact": impact,
            "sectors": sectors[:3],
            "etfs": etf_list,
            "holding_relevant": holding_rel,
            "logic": "命中「%s」→ 关联：%s；情绪词 %d 多 / %d 空，规则初判%s。" % (
                kw_show or "宏观词", "、".join(sectors[:3]) or "大盘情绪", pos, neg, direction),
            "watch": "关注官方后续披露与盘面量能确认。",
        })

    events.sort(key=lambda e: (e["_score"], e["_ts"]), reverse=True)
    events = events[:8]
    for e in events:
        e.pop("_score", None)
        e.pop("_ts", None)
    n_pos = sum(1 for e in events if e["direction"] == "利多")
    n_neg = sum(1 for e in events if e["direction"] == "利空")
    n_mid = len(events) - n_pos - n_neg
    sentiment = "偏多" if n_pos > n_neg + 1 else "偏空" if n_neg > n_pos + 1 else "中性"
    top_sectors = []
    for e in events:
        for s in e["sectors"]:
            if s not in top_sectors:
                top_sectors.append(s)
    overview = ("最近电报筛出 %d 条市场相关事件：利多 %d / 利空 %d / 中性 %d。"
                "主要关联板块：%s。方向为关键词规则初判，仅供参考。"
                % (len(events), n_pos, n_neg, n_mid,
                   "、".join(top_sectors[:4]) if top_sectors else "无"))

    return {"artifact": {
        "as_of": now.strftime("%Y-%m-%d %H:%M"),
        "sentiment": sentiment,
        "overview": overview,
        "events": events,
        "note": "" if events else "本次未筛到市场相关事件。",
    }}
