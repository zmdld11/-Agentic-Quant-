"""A 股版 Lopez-Lira：财联社电报 → LLM 情绪打分 → 前瞻情绪面板。

方法论出处：Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?"
(JFE)——让 LLM 给新闻打分，分数对股价方向有预测力。

数据源的坑（2026-09 实测，README 踩坑记录有档）：
- 东财个股新闻搜索接口（akshare stock_news_em）服务端变更，任何关键词都只返回
  用户区不返回新闻区；且其在 pandas3+pyarrow 下的正则清洗直接崩溃 → 弃用
- 改用**财联社电报**（akshare stock_info_global_cls，验证可用）：
  全市场级滚动快讯，每轮约 20 条。粒度从个股级变为市场级——
  对应的研究问题也调整为："电报情绪能否预测沪深300次日/短中期方向"

诚实约束：电报只有滚动最新 ~20 条，无历史存档 → 本模块定位是**前瞻采集**：
每天跑一次 --collect 攒面板（data/processed/sentiment_panel.parquet），
积累数周后才能做严格的 IC 检验；当下能出的是"今日市场情绪温度计"。

LLM 接口：OpenAI 兼容协议（默认智谱 GLM 端点），环境变量配置：
    LLM_BASE_URL  默认 https://open.bigmodel.cn/api/paas/v4
    LLM_API_KEY   必填才启用打分（无 key 时只采集不打分）
    LLM_MODEL     默认 glm-4-flash（便宜够用）
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pandas as pd

from quant.datasource import DATA_DIR, _retry

NEWS_CACHE = DATA_DIR / "news" / "cls_telegraph.parquet"
PANEL_FILE = DATA_DIR.parent / "processed" / "sentiment_panel.parquet"


def fetch_telegraph() -> pd.DataFrame:
    """拉取财联社电报最新一批，增量缓存（按标题+时间去重）。"""
    import akshare as ak  # noqa: PLC0415

    old = pd.read_parquet(NEWS_CACHE) if NEWS_CACHE.exists() else pd.DataFrame()
    raw = _retry(lambda: ak.stock_info_global_cls(symbol="全部"), times=3)
    new = raw.rename(columns={"标题": "title", "内容": "content",
                              "发布日期": "date", "发布时间": "time"})[
        ["title", "content", "date", "time"]].copy()
    df = pd.concat([old, new], ignore_index=True)
    df = df.drop_duplicates(subset=["title", "time"], keep="last")
    if "score" not in df.columns:
        df["score"] = pd.array([pd.NA] * len(df), dtype="Float64")
    else:
        df["score"] = df["score"].astype("Float64")
    NEWS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(NEWS_CACHE)
    return df


class NewsScorer:
    """OpenAI 兼容的批量新闻打分器（Lopez-Lira 式 prompt，市场级）。"""

    PROMPT = (
        "你是量化研究中的新闻情绪打分器，评估每条快讯对【A股大盘（沪深300）】"
        "【未来数个交易日】方向的指向。输出 -1 到 1 的分数：\n"
        "- 与股市基本无关（个股软文、行业展会、闲谈）→ 0 附近\n"
        "- 明显利好（货币宽松、经济数据超预期、重大改革利好）→ +0.3 ~ +1\n"
        "- 明显利空（外围暴跌、地缘冲突升级、流动性收紧）→ -0.3 ~ -1\n"
        "只输出 JSON：{{\"scores\": [依次与快讯等长的分数数组]}}\n\n"
        "快讯列表：\n{titles}"
    )

    def __init__(self):
        self.base_url = os.environ.get("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "glm-4-flash")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def score_batch(self, titles: list[str]) -> list[float | None]:
        """一批标题 → 分数列表（失败返回全 None）。每批 1 次 LLM 调用。"""
        import requests  # noqa: PLC0415

        prompt = self.PROMPT.format(
            titles="\n".join(f"{i+1}. {t}" for i, t in enumerate(titles)))
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "temperature": 0,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        resp.raise_for_status()
        return self.parse_scores(resp.json()["choices"][0]["message"]["content"], len(titles))

    @staticmethod
    def parse_scores(text: str, n: int) -> list[float | None]:
        """从模型回复解析分数数组；解析失败逐个置 None（不中断管线）。"""
        try:
            m = re.search(r"\{.*\}", text, re.S)
            data = json.loads(m.group(0)) if m else json.loads(text)
            scores = [float(s) for s in data["scores"]]
        except Exception:  # noqa: BLE001 - 模型输出不合法时降级
            return [None] * n
        if len(scores) != n:
            return [None] * n
        return [max(-1.0, min(1.0, s)) for s in scores]


def collect(max_llm_calls: int = 5) -> pd.DataFrame:
    """采集一轮电报 + 打分未评分项，更新当日情绪面板行。"""
    df = fetch_telegraph()
    scorer = NewsScorer()
    if not scorer.available:
        print(f"电报已缓存 {len(df)} 条。未检测到 LLM_API_KEY → 跳过打分"
              "（配置方法见 README『环境变量』）")
    else:
        unscored = df[df["score"].isna()]
        for start in range(0, len(unscored), 20):
            if start // 20 >= max_llm_calls:
                print(f"达到本轮 LLM 调用上限 {max_llm_calls}，其余下次再打分")
                break
            chunk = unscored.iloc[start:start + 20]
            try:
                scores = scorer.score_batch(chunk["title"].tolist())
            except Exception as e:  # noqa: BLE001 - 打分失败不影响采集
                print(f"  [warn] 打分失败: {type(e).__name__} {str(e)[:80]}")
                continue
            for idx, s in zip(chunk.index, scores):
                if s is not None:
                    df.loc[idx, "score"] = s
        df.to_parquet(NEWS_CACHE)
        print(f"电报 {len(df)} 条，其中已打分 {int(df['score'].notna().sum())} 条")

    # 面板：每个采集日一行（当日已打分条目的均值 = 市场情绪温度计）
    scored = df["score"].dropna()
    row = {"date": pd.Timestamp.now().normalize(), "n_news": len(df),
           "n_scored": int(df["score"].notna().sum()),
           "mean_score": float(scored.tail(30).mean()) if len(scored) else None}
    PANEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    old = pd.read_parquet(PANEL_FILE) if PANEL_FILE.exists() else pd.DataFrame()
    panel = pd.concat([old, pd.DataFrame([row])], ignore_index=True)
    panel = panel.drop_duplicates(subset=["date"], keep="last")
    panel.to_parquet(PANEL_FILE)
    print(f"情绪面板已更新: {PANEL_FILE}（累计 {len(panel)} 天）")
    if row["mean_score"] is not None:
        print(f"今日市场情绪温度计: {row['mean_score']:+.3f}")
    return panel


def digest(min_scored: int = 5) -> None:
    """今日市场情绪温度计 + 最看多/最看空快讯摘录。"""
    if not NEWS_CACHE.exists():
        print("电报缓存不存在：先运行 python main.py news --collect")
        return
    df = pd.read_parquet(NEWS_CACHE)
    scored = df[df["score"].notna()]
    if len(scored) < min_scored:
        print(f"已打分样本不足（{len(scored)} < {min_scored}）。"
              "配置 LLM_API_KEY 后重跑 --collect 即可。")
        return

    temp = float(scored["score"].tail(30).mean())
    bull = scored.nlargest(5, "score")[["title", "score"]]
    bear = scored.nsmallest(5, "score")[["title", "score"]]

    trend = ""
    if PANEL_FILE.exists():
        panel = pd.read_parquet(PANEL_FILE).dropna(subset=["mean_score"])
        if len(panel) >= 2:
            recent = panel.tail(10)
            trend = "\n近10日温度计走势: " + " → ".join(
                f"{v:+.2f}" for v in recent["mean_score"])

    lines = [
        f"===== A股市场情绪温度计 · 电报样本 {len(scored)} 条 =====",
        f"当前温度: {temp:+.3f}（-1极度恐慌 ~ +1极度贪婪）"
        f"  看多占比 {(scored['score'] > 0.1).mean():.0%} / 看空占比 {(scored['score'] < -0.1).mean():.0%}"
        + trend,
        "",
        "最看多快讯:",
        bull.to_string(index=False, formatters={"score": "{:+.2f}".format}),
        "",
        "最看空快讯:",
        bear.to_string(index=False, formatters={"score": "{:+.2f}".format}),
        "",
        "提醒: LLM情绪分是研究信号而非投资建议；样本为近期滚动电报，存在时效偏差。",
    ]
    text = "\n".join(lines)
    out = DATA_DIR.parent.parent / "results" / "news_digest"
    out.mkdir(parents=True, exist_ok=True)
    (out / "digest_latest.txt").write_text(text, encoding="utf-8")
    print(text)


def self_test() -> None:
    """无 key 也能跑的解析自测（验证管线关键路径）。"""
    cases = [
        ('{"scores": [0.8, -0.5, 0, 99]}', 4, [0.8, -0.5, 0.0, 1.0]),   # 越界截断
        ('前置废话 {"scores": [0.1, -0.2]} 后置废话', 2, [0.1, -0.2]),  # 从噪音提取 JSON
        ('模型拒绝回答', 2, [None, None]),                              # 解析失败降级
        ('{"scores": [0.5]}', 2, [None, None]),                         # 长度不符降级
    ]
    ok = True
    for text, n, want in cases:
        got = NewsScorer.parse_scores(text, n)
        status = "PASS" if got == want else "FAIL"
        ok = ok and got == want
        print(f"  [{status}] parse({text[:24]!r}, n={n}) -> {got}")
    print("自测通过" if ok else "自测失败")
