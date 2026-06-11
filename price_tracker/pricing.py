"""共享定价工具 — 均价算法、CNY 换算

本模块是 price_tracker 所有价格计算的唯一入口，禁止在 views/scraper/commands 中
各自实现除法或汇率换算。

Usage:
    from price_tracker.pricing import per_stick, avg_per_stick, convert_to_cny

    # 单支 CNY 价格
    ps = per_stick(price_cny=6857.19, box_size=25)  # → round(6857.19/25, 2) = 274.29

    # 多来源均价
    sources = [
        {'price_cny': 700, 'box_size': 25},
        {'price_cny': 685, 'box_size': 25},
    ]
    avg = avg_per_stick(sources)  # → round((28.0 + 27.4) / 2, 2) = 27.7

    # CNY 换算（含 fallback）
    cny = convert_to_cny(price=100, currency='USD')  # → 725.0 (假设汇率 7.25)
"""

from .models import ExchangeRate

# ── Fallback 汇率（DB 无数据时的兜底） ──────────────────────────────
FALLBACK_RATES = {
    'USD': 7.0,
    'CHF': 8.0,
    'EUR': 7.8,
}
DEFAULT_FALLBACK = 7.0


# ── 单支价 ──────────────────────────────────────────────────────────

def per_stick(price_cny: float, box_size: int | None) -> float | None:
    """整盒人民币价 ÷ 支数 → 单支 CNY（精度 2 位小数）

    如果 box_size 为 None/0 或 price_cny 为 None，返回 None。
    """
    if price_cny is None or not box_size or box_size <= 0:
        return None
    return round(price_cny / box_size, 2)


# ── 多来源均价 ──────────────────────────────────────────────────────

def avg_per_stick(sources: list[dict]) -> float | None:
    """多来源单支价的算术平均（精度 2 位小数）

    sources 列表中每项应包含 'price_cny' 和 'box_size' 键。

    算法（与前端详情页 VariantTable/PriceChart 一致）：
      1. 每来源：先 round(price_cny / box_size, 2) → 获得该来源的 per_stick
      2. 所有来源的 per_stick 求算术平均
      3. 最终 round(avg, 2)

    Returns:
        均价 float，或 None（无有效来源）
    """
    sticks = []
    for s in sources:
        ps = per_stick(s.get('price_cny'), s.get('box_size'))
        if ps is not None:
            sticks.append(ps)
    if not sticks:
        return None
    return round(sum(sticks) / len(sticks), 2)


# ── CNY 换算 ────────────────────────────────────────────────────────

def convert_to_cny(price: float, currency: str) -> float:
    """原币种价格 → 人民币（含 fallback）

    优先级：DB 汇率表 → FALLBACK_RATES → DEFAULT_FALLBACK
    """
    if price is None:
        return None
    result = ExchangeRate.cny_convert(price, currency)
    if result is not None:
        return result
    rate = FALLBACK_RATES.get(currency.upper(), DEFAULT_FALLBACK)
    return round(price * rate, 2)
