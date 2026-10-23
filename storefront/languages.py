"""Locale-safe rendering helpers for existing storefront information."""

from __future__ import annotations


LOCALES = ("zh", "ru", "en")

# Existing home copy prepared by prepare_storefront_content; fallback rendering
# reads it without changing the corresponding StoreTranslation publication state.
HOME_COPY = {
    "zh": {
        "title": "莫斯科雪茄门店与现货 | CigarDomTabaka",
        "description": "查看 CigarDomTabaka 莫斯科雪茄门店的现货、盒装规格与价格，按品牌浏览并联系门店确认购买。",
        "body": "浏览当前可售的盒装雪茄，查看品牌、规格与价格。选择商品后，请联系门店确认现货和购买安排。人民币与美元换算仅供参考，正式标价以卢布为准。",
    },
    "ru": {
        "title": "Сигары в Москве — наличие и цены | CigarDomTabaka",
        "description": "Сигары в наличии в CigarDomTabaka в Москве: бренды, форматы коробок и цены. Свяжитесь с магазином для подтверждения покупки.",
        "body": "Выберите сигары из доступных коробок, сравните бренды, форматы и цены. Перед покупкой свяжитесь с магазином, чтобы подтвердить наличие и договориться о покупке. Пересчёт в CNY и USD приведён для справки; основная цена указана в рублях.",
    },
    "en": {
        "title": "Cigars in Moscow — stock and prices | CigarDomTabaka",
        "description": "Browse cigars in stock at CigarDomTabaka in Moscow, with brands, box sizes and prices. Contact the store to confirm your purchase.",
        "body": "Explore available boxes of cigars, compare brands and sizes, and view prices. Contact the store to confirm availability and purchase arrangements. CNY and USD conversions are for reference; the listed retail price is in rubles.",
    },
}

# These are names for existing vitola values, not product descriptions.
VITOLA_LABELS = {
    "Robusto": {"zh": "罗布图", "ru": "Робусто", "en": "Robusto"},
    "Robusto Extra": {"zh": "特级罗布图", "ru": "Робусто Экстра", "en": "Robusto Extra"},
    "Petit Robusto": {"zh": "小罗布图", "ru": "Петит Робусто", "en": "Petit Robusto"},
    "Corona": {"zh": "皇冠型", "ru": "Корона", "en": "Corona"},
    "Petit Corona": {"zh": "小皇冠型", "ru": "Петит Корона", "en": "Petit Corona"},
    "Grande": {"zh": "大皇冠型", "ru": "Гранде", "en": "Grande"},
    "Churchill": {"zh": "丘吉尔型", "ru": "Черчилль", "en": "Churchill"},
    "Double Corona": {"zh": "双皇冠型", "ru": "Двойная Корона", "en": "Double Corona"},
    "Lancero": {"zh": "长矛型", "ru": "Лансеро", "en": "Lancero"},
    "Panetela": {"zh": "细长型", "ru": "Панатела", "en": "Panetela"},
    "Lonsdale": {"zh": "朗斯代尔型", "ru": "Лонсдейл", "en": "Lonsdale"},
    "Torpedo": {"zh": "鱼雷型", "ru": "Торпедо", "en": "Torpedo"},
    "Belicoso": {"zh": "贝里科索型", "ru": "Беликосо", "en": "Belicoso"},
    "Piramides": {"zh": "金字塔型", "ru": "Пирамидес", "en": "Piramides"},
    "Perfecto": {"zh": "完美型", "ru": "Перфекто", "en": "Perfecto"},
    "Figurado": {"zh": "异型雪茄", "ru": "Фигурадо", "en": "Figurado"},
    "Cañonazo": {"zh": "加农炮型", "ru": "Каньонасо", "en": "Cañonazo"},
    "Short Robusto": {"zh": "短罗布图", "ru": "Шорт Робусто", "en": "Short Robusto"},
    "Mareva": {"zh": "马雷瓦型", "ru": "Марева", "en": "Mareva"},
    "Petit Edmundo": {"zh": "小埃德蒙多型", "ru": "Петит Эдмундо", "en": "Petit Edmundo"},
    "Edmundo": {"zh": "埃德蒙多型", "ru": "Эдмундо", "en": "Edmundo"},
    "Short Churchill": {"zh": "短丘吉尔型", "ru": "Шорт Черчилль", "en": "Short Churchill"},
    "Dalias": {"zh": "达利亚斯型", "ru": "Далиас", "en": "Dalias"},
    "Julieta No. 2": {"zh": "朱丽叶二号型", "ru": "Хулиета № 2", "en": "Julieta No. 2"},
    "Minuto": {"zh": "迷你型", "ru": "Минуто", "en": "Minuto"},
}

SPECIFICATION_LABELS = {
    "zh": {"name": "名称", "vitola": "型号", "length": "长度", "ring_gauge": "环径"},
    "ru": {"name": "Модель", "vitola": "Витола", "length": "Длина", "ring_gauge": "Диаметр кольца"},
    "en": {"name": "Name", "vitola": "Vitola", "length": "Length", "ring_gauge": "Ring gauge"},
}


def vitola_label(value: str, locale: str) -> str:
    """Translate a known specification label; preserve unknown source text."""
    labels = VITOLA_LABELS.get(value)
    return labels.get(locale, value) if labels else value


def specification_summary(*, name: str, vitola: str, length, ring_gauge, locale: str) -> str:
    """Format only existing model identity and specification facts."""
    labels = SPECIFICATION_LABELS.get(locale, SPECIFICATION_LABELS["en"])
    parts = [f"{labels['name']}: {name}"] if name else []
    if vitola:
        parts.append(f"{labels['vitola']}: {vitola_label(vitola, locale)}")
    if length is not None:
        parts.append(f"{labels['length']}: {_format_number(length)} mm")
    if ring_gauge is not None:
        parts.append(f"{labels['ring_gauge']}: {_format_number(ring_gauge)}")
    return " · ".join(parts)


def _format_number(value) -> str:
    rendered = str(value)
    if rendered.endswith(".0"):
        return rendered[:-2]
    return rendered


def locale_content_locale(locale: str, complete: bool) -> str:
    """Describe the actual source language used by a page read model."""
    if locale == "zh" or complete:
        return locale
    return "en"
