"""Search metadata derived from public page data, without changing display names."""

import re
import unicodedata


COPY = {
    "zh": {
        "catalog": "雪茄目录",
        "brand_title": "{brand}雪茄 — 莫斯科",
        "catalog_description": "浏览 {site} 的雪茄目录，按品牌查看商品资料、规格与已公布的报价；请联系门店确认当前供应情况。",
        "product_locality": "莫斯科雪茄",
        "page": "第 {number} 页",
    },
    "ru": {
        "catalog": "Каталог сигар",
        "brand_title": "Сигары {brand} в Москве",
        "catalog_description": "Каталог сигар {site}: информация о моделях, характеристики и опубликованные цены по брендам. Уточняйте наличие в магазине.",
        "product_locality": "сигары в Москве",
        "page": "Страница {number}",
    },
    "en": {
        "catalog": "Cigar catalogue",
        "brand_title": "{brand} cigars in Moscow",
        "catalog_description": "Browse the {site} cigar catalogue by brand for product information, specifications and published prices. Contact the store to confirm availability.",
        "product_locality": "Cigars in Moscow",
        "page": "Page {number}",
    },
}


def _text(value):
    return str(value or "").strip()


def _normalized(value):
    # Normalize punctuation/spacing for repeated names, not for public URLs or images.
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _contains_name(title, name):
    title, name = _normalized(title), _normalized(name)
    if not name:
        return False
    # Chinese brand and model names commonly have no separating whitespace.
    if re.search(r"[\u3400-\u9fff]", name):
        return name in title
    return title == name or f" {name} " in f" {title} "


def enrich_page_metadata(pages):
    """Add SEO titles after catalog assembly; leave display titles and URLs intact.

    Product/brand/home descriptions are reviewed content and remain unchanged.
    The generated catalogue alone gets its own description instead of inheriting
    the homepage's current-stock description. No availability claims are inferred.
    """
    for page in pages.values():
        copy = COPY.get(page.get("locale"), COPY["en"])
        site = _text((page.get("site") or {}).get("name")) or "CigarDomTabaka"
        title = _text(page.get("title"))
        override = _text(page.get("seo_title_override")) if page.get("view") != "catalog" else ""
        if page.get("view") == "catalog":
            title = copy["catalog"]
            page["description"] = copy["catalog_description"].format(site=site)
        elif override:
            # Store the reviewed title separately from the generated result, so
            # enrichment stays idempotent and pagination precedes one site suffix.
            title = re.sub(rf"(?:\s*\|\s*{re.escape(site)})+\s*$", "", override, flags=re.IGNORECASE).strip()
        elif page.get("kind") == "product":
            product = page.get("product") or {}
            title = _text(product.get("name")) or _text(product.get("english_name")) or title
            brand = _text(product.get("brand"))
            if brand and not _contains_name(title, brand):
                title = f"{brand} {title}".strip()
            title = " — ".join(filter(None, [title, copy["product_locality"]]))
        elif page.get("kind") == "brand":
            # Every language serves the Moscow store's brand searches.
            # Keep this in metadata: the reviewed brand history stays unchanged.
            title = copy["brand_title"].format(brand=title)

        number = (page.get("pagination") or {}).get("page", 1)
        if isinstance(number, int) and number > 1:
            title = " — ".join(filter(None, [title, copy["page"].format(number=number)]))
        if override or not _contains_name(title, site):
            title = " | ".join(filter(None, [title, site]))
        page["seo_title"] = title
