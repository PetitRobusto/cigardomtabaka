"""Search metadata derived from public page data, without changing display names."""

from decimal import Decimal, InvalidOperation
import re
import unicodedata


COPY = {
    "zh": {
        "catalog": "雪茄目录",
        "catalog_description": "浏览 {site} 的雪茄目录，按品牌查看商品资料、规格与已公布的报价；请联系门店确认当前供应情况。",
        "information": "雪茄资料",
        "specifications": "规格资料",
        "prices": "资料与价格",
        "specifications_prices": "规格与价格",
        "page": "第 {number} 页",
    },
    "ru": {
        "catalog": "Каталог сигар",
        "brand_title": "Сигары {brand} в Москве",
        "catalog_description": "Каталог сигар {site}: информация о моделях, характеристики и опубликованные цены по брендам. Уточняйте наличие в магазине.",
        "information": "Информация о сигаре",
        "specifications": "Характеристики",
        "prices": "Информация и цены",
        "specifications_prices": "Характеристики и цены",
        "page": "Страница {number}",
    },
    "en": {
        "catalog": "Cigar catalogue",
        "catalog_description": "Browse the {site} cigar catalogue by brand for product information, specifications and published prices. Contact the store to confirm availability.",
        "information": "Cigar information",
        "specifications": "Specifications",
        "prices": "Information and prices",
        "specifications_prices": "Specifications and prices",
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


def _has_public_price(product):
    for offer in product.get("offers") or []:
        try:
            price = Decimal(str(offer.get("price_rub")))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if price.is_finite() and price > 0:
            return True
    return False


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
        if page.get("view") == "catalog":
            title = copy["catalog"]
            page["description"] = copy["catalog_description"].format(site=site)
        elif page.get("kind") == "product":
            product = page.get("product") or {}
            title = _text(product.get("name")) or _text(product.get("english_name")) or title
            brand = _text(product.get("brand"))
            if brand and not _contains_name(title, brand):
                title = f"{brand} {title}".strip()
            has_specs = bool(product.get("vitola") or product.get("length") or product.get("ring_gauge"))
            has_price = _has_public_price(product)
            label = "specifications_prices" if has_specs and has_price else "specifications" if has_specs else "prices" if has_price else "information"
            title = " — ".join(filter(None, [title, copy[label]]))
        elif page.get("kind") == "brand":
            # Russian brand pages serve the Moscow store's brand searches.
            # Keep this in metadata: the reviewed brand history stays unchanged.
            title = (copy["brand_title"].format(brand=title) if "brand_title" in copy
                     else " — ".join(filter(None, [title, copy["catalog"]])))

        number = (page.get("pagination") or {}).get("page", 1)
        if isinstance(number, int) and number > 1:
            title = " — ".join(filter(None, [title, copy["page"].format(number=number)]))
        if not _contains_name(title, site):
            title = " | ".join(filter(None, [title, site]))
        page["seo_title"] = title
