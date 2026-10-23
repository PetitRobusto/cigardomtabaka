"""Locale-safe rendering helpers for existing storefront information."""

from __future__ import annotations


LOCALES = ("zh", "ru", "en")

# Existing home copy prepared by prepare_storefront_content; fallback rendering
# reads it without changing the corresponding StoreTranslation publication state.
HOME_COPY = {
    "zh": {
        "title": "莫斯科古巴雪茄专业服务商",
        "description": "CigarDomTabaka 莫斯科门店有超过50种古巴雪茄，专业茄房，正品保证，平价销售。",
        "body": "CigarDomTabaka 莫斯科门店有超过50种古巴雪茄，专业茄房，正品保证，平价销售。",
    },
    "ru": {
        "title": "Специалист по кубинским сигарам в Москве",
        "description": "В московском магазине «Сигар Дом Табака» представлено более 50 видов кубинских сигар. Профессиональная хьюмидорная комната, гарантия подлинности и доступные цены.",
        "body": "В московском магазине «Сигар Дом Табака» представлено более 50 видов кубинских сигар. Профессиональная хьюмидорная комната, гарантия подлинности и доступные цены.",
    },
    "en": {
        "title": "Your Cuban cigar specialist in Moscow",
        "description": "CigarDomTabaka in Moscow offers over 50 varieties of Cuban cigars, a professional walk-in humidor, guaranteed authenticity and affordable prices.",
        "body": "CigarDomTabaka in Moscow offers over 50 varieties of Cuban cigars, a professional walk-in humidor, guaranteed authenticity and affordable prices.",
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
