"""Build the public, read-only storefront page catalog."""

from __future__ import annotations

import re
import unicodedata
import hashlib
import json
from collections import defaultdict
from urllib.parse import urlsplit, urlencode
from django.db.models import Sum

from cigars.models import Brand, Cigar, CigarPrice, PurchaseBatch
from .models import ProductListing, StoreSettings, StoreTranslation


LOCALES = ("zh", "ru", "en")
PAGE_SIZE = 24
PRIORITY_BRANDS = ("Cohiba", "Montecristo", "Romeo y Julieta", "Partagás", "Hoyo de Monterrey", "H. Upmann")


def _locale_prefix(locale: str) -> str:
    return "" if locale == "zh" else f"/{locale}"


def _home_path(locale: str) -> str:
    return _locale_prefix(locale) + "/"


def _brand_path(locale: str, slug: str) -> str:
    return f"{_locale_prefix(locale)}/brand/{slug}"


def _product_path(locale: str, cigar_id: int, slug: str) -> str:
    return f"{_locale_prefix(locale)}/cigar/{cigar_id}/{slug}"


def _product_slug(cigar: Cigar) -> str:
    source = " ".join(filter(None, [cigar.brand, cigar.english_name, cigar.release_type, cigar.release_name]))
    decomposed = unicodedata.normalize("NFD", source).lower()
    decomposed = "".join(char for char in decomposed if not unicodedata.combining(char))
    decomposed = re.sub(r"[^a-z0-9_\s-]", "", decomposed)
    slug = re.sub(r"-+", "-", re.sub(r"\s+", "-", decomposed)).strip("-")[:100].rstrip("-")
    return slug or "cigar"


def _clean_path(path: str) -> str:
    path = "/" + str(path or "").lstrip("/")
    path = re.sub(r"/{2,}", "/", path)
    if path.rstrip("/") in {"/ru", "/en"}:
        return path.rstrip("/") + "/"
    return path.rstrip("/") or "/"


def _safe_media_url(field) -> str:
    try:
        value = field.url if field and field.name else ""
        if value and not urlsplit(value).scheme and not value.startswith("/"):
            value = "/" + value
        return value
    except (ValueError, OSError):
        return ""


def _site_data(locale: str, home_translation: StoreTranslation | None, store: StoreSettings | None) -> dict:
    data = {
        "name": store.name if store else "CigarDomTabaka",
        "address": "",
        "phone": "",
        "wechat": "",
        "map_url": "",
        "photo": "",
        "points_of_sales": "",
        "hours": "",
    }
    if store and store.details_verified:
        data.update({
            "address": store.address,
            "phone": store.phone,
            "wechat": store.wechat,
            "map_url": store.map_url,
            "photo": _safe_media_url(store.photo),
            "points_of_sales": _safe_media_url(store.points_of_sales),
            "hours": home_translation.hours if home_translation else "",
        })
    return data


def _brand_rows() -> dict[str, Brand]:
    return {brand.slug: brand for brand in Brand.objects.all()}


def _image_rows(cigar: Cigar) -> list:
    rows = list(cigar.images.all())
    if not rows:
        return rows
    primary = next((row for row in rows if row.is_primary and row.image_type != "band"), None)
    if primary is None:
        primary = next((row for row in rows if row.image_type != "band"), rows[0])
    return [primary, *(row for row in rows if row.pk != primary.pk)]


def _images(cigar: Cigar, image_rows: list | None = None) -> list[str]:
    """Return full-size image URLs for the product detail gallery."""
    rows = image_rows if image_rows is not None else _image_rows(cigar)
    result = []
    for image in rows:
        url = _safe_media_url(image.image) or _safe_media_url(image.thumbnail)
        if url and url not in result:
            result.append(url)
    fallback = _safe_media_url(cigar.image) or cigar.image_url
    if fallback and fallback not in result:
        result.append(fallback)
    return result


def _card_image(cigar: Cigar, image_rows: list | None = None) -> str:
    """Prefer the primary thumbnail for cards; retain source fallbacks."""
    rows = image_rows if image_rows is not None else _image_rows(cigar)
    if rows:
        primary = rows[0]
        url = _safe_media_url(primary.thumbnail) or _safe_media_url(primary.image)
        if url:
            return url
    return _safe_media_url(cigar.image) or cigar.image_url


def _available_boxes() -> dict[tuple[int, int], int]:
    totals = defaultdict(int)
    batches = PurchaseBatch.objects.filter(
        reversed_at__isnull=True,
        available_box_quantity__gt=0,
        box_size__isnull=False,
        cigar__deleted_at__isnull=True,
    ).values("cigar_id", "box_size").annotate(total=Sum("available_box_quantity"))
    for row in batches:
        totals[(row["cigar_id"], row["box_size"])] = row["total"] or 0
    return totals


def _available_sticks() -> dict[int, int]:
    """Read sellable loose sticks without converting boxes or exposing quantities."""
    return {
        row["cigar_id"]: row["total"]
        for row in PurchaseBatch.objects.filter(
            reversed_at__isnull=True,
            available_stick_quantity__gt=0,
            cigar__deleted_at__isnull=True,
        ).values("cigar_id").annotate(total=Sum("available_stick_quantity"))
    }


def _known_inventory() -> set[int]:
    return set(PurchaseBatch.objects.values_list("cigar_id", flat=True).distinct())


def _published_listings() -> set[int]:
    return set(ProductListing.objects.filter(published=True, withdrawn=False).values_list("cigar_id", flat=True))


def _product_data(cigar: Cigar, locale: str, translation: StoreTranslation | None,
                  brands: dict[str, Brand], stock: dict[tuple[int, int], int],
                  listings: set[int], prices: dict[int, list[CigarPrice]],
                  known_inventory: set[int],
                  brand_translations: dict[str, dict[str, StoreTranslation]],
                  stick_stock: dict[int, int] | None = None) -> dict:
    brand = next((b for b in brands.values() if b.english_name == cigar.brand), None)
    brand_slug = brand.slug if brand else ""
    slug = _product_slug(cigar)
    path = _product_path(locale, cigar.pk, slug)
    if translation:
        name = translation.title
        description = translation.description
        aliases = translation.aliases.split()
        body = translation.body
    else:
        name = cigar.name or cigar.english_name
        description = " · ".join(filter(None, [cigar.vitola_cn or cigar.vitola, cigar.common_name_cn or cigar.common_name]))
        aliases = [x for x in (cigar.english_name, cigar.name, cigar.common_name, cigar.common_name_cn) if x]
        body = description
    if not description:
        description = f"{cigar.brand} {cigar.english_name}"
        if cigar.vitola:
            description += f" · {cigar.vitola}"
        body = description
    offers = []
    has_sticks = bool((stick_stock or {}).get(cigar.pk, 0) > 0)
    stock_sizes = {box_size for (cigar_id, box_size), quantity in stock.items()
                   if cigar_id == cigar.pk and quantity > 0}
    total_stock = sum(stock[(cigar.pk, box_size)] for box_size in stock_sizes)
    if cigar.pk in listings:
        active_prices = {price.box_size: price for price in prices.get(cigar.pk, [])
                         if price.box_size > 0}
        for box_size in sorted(set(active_prices) | stock_sizes):
            price = active_prices.get(box_size)
            quantity = stock.get((cigar.pk, box_size), 0)
            public_price = price.retail_price_rub if price and price.retail_price_rub and price.retail_price_rub > 0 else None
            offers.append({
                "box_size": box_size,
                "price_rub": str(public_price) if public_price is not None else None,
                "in_stock": quantity > 0,
            })
        if has_sticks:
            offers.append({"sale_unit": "stick", "box_size": None, "price_rub": None, "in_stock": True})
    image_rows = _image_rows(cigar)
    images = _images(cigar, image_rows)
    return {
        "id": cigar.pk,
        "name": name,
        "english_name": cigar.english_name,
        "brand": (
            brand_translations.get(locale, {}).get(brand.slug).title
            if brand and locale != "zh" and brand.slug in brand_translations.get(locale, {})
            else (brand.english_name if locale != "zh" else brand.name or brand.english_name)
            if brand else cigar.brand
        ),
        "brand_slug": brand_slug,
        "path": path,
        "description": description,
        "aliases": aliases,
        "image_url": _card_image(cigar, image_rows),
        "images": images,
        "image_kinds": {_safe_media_url(row.image) or _safe_media_url(row.thumbnail): row.image_type for row in image_rows},
        "vitola": cigar.vitola_cn or cigar.vitola if locale == "zh" else cigar.vitola,
        "length": cigar.length,
        "ring_gauge": cigar.ring_gauge,
        "availability": (
            "catalog" if cigar.pk not in listings
            else "in_stock" if total_stock > 0 or has_sticks
            else "out_of_stock" if cigar.pk in known_inventory
            else "catalog"
        ),
        "offers": offers,
    }


def _pagination(page: int, total: int, base_path: str) -> tuple[list[int], dict]:
    count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, count))
    def url(number):
        if number is None:
            return None
        return base_path if number == 1 else f"{base_path}?page={number}"
    return list(range(1, count + 1)), {
        "page": page,
        "total_pages": count,
        "previous": url(page - 1) if page > 1 else None,
        "next": url(page + 1) if page < count else None,
    }


def _alternates(paths_by_locale: dict[str, str]) -> list[dict[str, str]]:
    return [{"locale": locale, "path": paths_by_locale[locale]}
            for locale in LOCALES if locale in paths_by_locale]


def _published_translations() -> dict[tuple[str, str, str], StoreTranslation]:
    return {
        (row.kind, row.key, row.locale): row
        for row in StoreTranslation.objects.filter(published=True)
        if all(value.strip() for value in (row.title, row.description, row.body))
    }


def _translation_dependencies(page: dict, translations: dict) -> list[list[str]]:
    """Record the reviewed text actually used in this page, including visible cards."""
    locale = page["locale"]
    used = set()

    def include(kind, key):
        dependency = (kind, str(key), locale)
        if dependency in translations:
            used.add(dependency)

    if page["kind"] == "home":
        include("home", "home")
    elif page["kind"] == "brand":
        include("brand", page["path"].split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1])
    if locale != "zh" or page["site"].get("hours"):
        include("home", "home")
    products = [*page["products"]]
    if page["product"]:
        products.append(page["product"])
    for product in products:
        include("product", product["id"])
        if locale != "zh":
            include("brand", product["brand_slug"])
    for brand in page["brands"]:
        include("brand", brand["slug"])
    for brand in page.get("navigation", {}).get("brands", []):
        include("brand", brand["slug"])
    return [list(dependency) for dependency in sorted(used)]


def build_pages() -> dict[str, dict]:
    """Return all currently publishable pages, keyed by their canonical path."""
    brands = _brand_rows()
    store = StoreSettings.objects.filter(pk=1).first()
    cigars = list(Cigar.objects.filter(deleted_at__isnull=True).select_related().prefetch_related("images"))
    stock = _available_boxes()
    stick_stock = _available_sticks()
    known_inventory = _known_inventory()
    listings = _published_listings()
    prices_by_cigar = defaultdict(list)
    for price in CigarPrice.objects.filter(is_active=True).select_related("cigar").order_by("sort_order", "box_size"):
        prices_by_cigar[price.cigar_id].append(price)

    translations = _published_translations()
    brand_translations = {
        locale: {key: row for (kind, key, row_locale), row in translations.items()
                 if kind == "brand" and row_locale == locale}
        for locale in LOCALES
    }
    withdrawn = set(ProductListing.objects.filter(withdrawn=True).values_list("cigar_id", flat=True))
    result: dict[str, dict] = {}

    # Product pages: legacy Chinese catalog records remain available without a listing.
    for locale in LOCALES:
        for cigar in cigars:
            if cigar.pk in withdrawn:
                continue
            translation = translations.get(("product", str(cigar.pk), locale))
            brand = next((b for b in brands.values() if b.english_name == cigar.brand), None)
            if locale != "zh" and (
                not translation
                or ("home", "home", locale) not in translations
                or not brand
                or brand.slug not in brand_translations[locale]
            ):
                continue
            product = _product_data(cigar, locale, translation, brands, stock, listings, prices_by_cigar, known_inventory, brand_translations, stick_stock)
            available_locales = {}
            for other in LOCALES:
                other_brand_ok = bool(brand and (other == "zh" or brand.slug in brand_translations[other]))
                if other == "zh" or (
                    other_brand_ok
                    and ("home", "home", other) in translations
                    and ("product", str(cigar.pk), other) in translations
                ):
                    available_locales[other] = _product_path(other, cigar.pk, _product_slug(cigar))
            breadcrumbs = []
            if locale == "zh" or ("home", "home", locale) in translations:
                home_title = translations.get(("home", "home", locale)).title if locale != "zh" else "Home"
                breadcrumbs.append({"label": home_title, "path": _home_path(locale)})
            if brand and (locale == "zh" or brand.slug in brand_translations[locale]):
                brand_title = brand_translations[locale][brand.slug].title if locale != "zh" else brand.name or brand.english_name
                breadcrumbs.append({"label": brand_title, "path": _brand_path(locale, brand.slug)})
            breadcrumbs.append({"label": product["name"], "path": product["path"]})
            title = translation.title if translation else product["name"]
            page = {
                "locale": locale, "kind": "product", "path": product["path"],
                "title": title, "description": translation.description if translation else product["description"],
                "body": translation.body if translation else product["description"],
                "site": _site_data(locale, translations.get(("home", "home", locale)), store),
                "products": [], "product": product, "brands": [],
                "alternates": _alternates(available_locales), "breadcrumbs": breadcrumbs,
                "pagination": {"page": 1, "total_pages": 1, "previous": None, "next": None},
            }
            result[page["path"]] = page

    # Brand pages: zh can use existing brand names; translated pages require publication.
    for locale in LOCALES:
        locale_brand_translations = brand_translations[locale]
        for brand in brands.values():
            translation = locale_brand_translations.get(brand.slug)
            if locale != "zh" and (not translation or ("home", "home", locale) not in translations):
                continue
            brand_path = _brand_path(locale, brand.slug)
            rows = []
            for cigar in cigars:
                if cigar.pk in withdrawn:
                    continue
                if cigar.brand != brand.english_name:
                    continue
                cigar_translation = translations.get(("product", str(cigar.pk), locale))
                if locale != "zh" and (
                    not cigar_translation
                    or ("home", "home", locale) not in translations
                    or brand.slug not in brand_translations[locale]
                ):
                    continue
                rows.append(_product_data(cigar, locale, cigar_translation, brands, stock, listings, prices_by_cigar, known_inventory, brand_translations, stick_stock))
            rows.sort(key=lambda p: (p["availability"] != "in_stock", p["name"].casefold(), p["id"]))
            _, pagination = _pagination(1, len(rows), brand_path)
            page_rows = rows[:PAGE_SIZE]
            paths = {locale: brand_path}
            for other in LOCALES:
                if other == "zh" or (
                    brand.slug in brand_translations[other]
                    and ("home", "home", other) in translations
                ):
                    paths[other] = _brand_path(other, brand.slug)
            title = translation.title if translation else (brand.name or brand.english_name)
            description = translation.description if translation else brand.english_name
            page = {
                "locale": locale, "kind": "brand", "path": brand_path,
                "total_products": len(rows),
                "title": title, "description": description,
                "body": translation.body if translation else "",
                "site": _site_data(locale, translations.get(("home", "home", locale)), store),
                "products": page_rows, "product": None,
                "brands": [], "alternates": _alternates(paths),
                "breadcrumbs": ([{"label": translations[("home", "home", locale)].title, "path": _home_path(locale)}]
                                 if locale != "zh" and ("home", "home", locale) in translations
                                 else [{"label": "Home", "path": _home_path(locale)}] if locale == "zh" else [])
                                + [{"label": title, "path": brand_path}],
                "pagination": pagination,
            }
            result[brand_path] = page
            for page_number in range(2, pagination["total_pages"] + 1):
                page_url = f"{brand_path}?page={page_number}"
                page_copy = dict(page)
                page_copy["path"] = page_url
                page_copy["products"] = rows[(page_number - 1) * PAGE_SIZE:page_number * PAGE_SIZE]
                _, page_copy["pagination"] = _pagination(page_number, len(rows), brand_path)
                result[page_url] = page_copy

    # Home pages require an explicitly reviewed translation in each locale.
    for locale in LOCALES:
        translation = translations.get(("home", "home", locale))
        if not translation:
            continue
        rows = []
        for cigar in cigars:
            if cigar.pk in withdrawn or cigar.pk not in listings:
                continue
            if not stick_stock.get(cigar.pk) and not any(stock.get((cigar.pk, box_size), 0) > 0 for (cigar_id, box_size) in stock if cigar_id == cigar.pk):
                continue
            if locale != "zh":
                brand = next((b for b in brands.values() if b.english_name == cigar.brand), None)
                if (not translations.get(("product", str(cigar.pk), locale))
                        or not brand or brand.slug not in brand_translations[locale]):
                    continue
            rows.append(_product_data(cigar, locale, translations.get(("product", str(cigar.pk), locale)), brands, stock, listings, prices_by_cigar, known_inventory, brand_translations, stick_stock))
        rows.sort(key=lambda p: (p["brand"].casefold(), p["name"].casefold(), p["id"]))
        home = _home_path(locale)
        _, pagination = _pagination(1, len(rows), home)
        visible_brands = []
        for brand in brands.values():
            brand_translation = brand_translations[locale].get(brand.slug)
            if locale != "zh" and not brand_translation:
                continue
            visible_brands.append({
                "name": brand_translation.title if brand_translation else brand.name or brand.english_name,
                "english_name": brand.english_name,
                "slug": brand.slug,
                "path": _brand_path(locale, brand.slug),
            })
        visible_brands.sort(key=lambda row: row["name"].casefold())
        paths = {other: _home_path(other) for other in LOCALES
                 if ("home", "home", other) in translations}
        result[home] = {
            "locale": locale, "kind": "home", "path": home,
            "total_products": len(rows),
            "title": translation.title, "description": translation.description, "body": translation.body,
            "site": _site_data(locale, translation, store),
            "products": rows[:PAGE_SIZE], "product": None, "brands": visible_brands,
            "alternates": _alternates(paths), "breadcrumbs": [{"label": translation.title, "path": home}],
            "pagination": pagination,
        }
        for page_number in range(2, pagination["total_pages"] + 1):
            page_url = f"{home}?page={page_number}"
            page_copy = dict(result[home])
            page_copy["path"] = page_url
            page_copy["products"] = rows[(page_number - 1) * PAGE_SIZE:page_number * PAGE_SIZE]
            _, page_copy["pagination"] = _pagination(page_number, len(rows), home)
            result[page_url] = page_copy

    _add_browsing_context(result, brands, brand_translations)

    # A paginated page must alternate to the matching page in another locale.
    # A target page may not exist when fewer products are published there.
    for page in result.values():
        page["translation_dependencies"] = _translation_dependencies(page, translations)
        page_number = page.get("pagination", {}).get("page", 1)
        page["browsing_alternates"] = [
            {**alternate, "path": alternate["path"].split("?", 1)[0]}
            for alternate in page.get("alternates", [])
            if alternate["path"].split("?", 1)[0] in result
        ]
        alternates = []
        for alternate in page.get("alternates", []):
            base_path = alternate["path"].split("?", 1)[0]
            target_path = base_path if page_number == 1 else f"{base_path}?page={page_number}"
            if target_path in result:
                alternates.append({**alternate, "path": target_path})
        page["alternates"] = alternates
    return result


def _catalog_path(locale):
    return _locale_prefix(locale) + "/catalog"


def _add_browsing_context(pages, brands, brand_translations):
    """Add a separate stock shelf without changing legacy catalogue URLs."""
    stock_by_locale = {}
    for locale in LOCALES:
        stock_by_locale[locale] = [
            product for page in pages.values()
            if page["locale"] == locale and page["kind"] == "home"
            for product in page["products"]
        ]
    for locale in LOCALES:
        home = pages.get(_home_path(locale))
        if not home:
            continue
        stock = stock_by_locale[locale]
        title = {"zh": "现货商品", "ru": "Сигары в наличии", "en": "In-stock cigars"}[locale]
        base = _catalog_path(locale)
        _, pagination = _pagination(1, len(stock), base)
        for number in range(1, pagination["total_pages"] + 1):
            path = base if number == 1 else f"{base}?page={number}"
            _, current = _pagination(number, len(stock), base)
            pages[path] = {
                **home, "path": path, "view": "catalog", "title": title,
                "products": stock[(number - 1) * PAGE_SIZE:number * PAGE_SIZE],
                "breadcrumbs": [{"label": home["title"], "path": home["path"]}, {"label": title, "path": base}],
                "pagination": current,
                "alternates": [{"locale": alt["locale"], "path": _catalog_path(alt["locale"])} for alt in home["alternates"]],
            }
    rows_by_path = defaultdict(list)
    for page in pages.values():
        rows_by_path[page["path"].split("?", 1)[0]].extend(page["products"])
    for page in pages.values():
        locale = page["locale"]
        stock = stock_by_locale[locale]
        home = pages.get(_home_path(locale))
        stock_brands = {p["brand_slug"] for p in stock}
        navigation_brands = []
        if home:
            for brand in brands.values():
                if brand.english_name not in PRIORITY_BRANDS and brand.slug not in stock_brands:
                    continue
                translation = brand_translations[locale].get(brand.slug)
                navigation_brands.append({
                    "name": translation.title if translation else (brand.name or brand.english_name) if locale == "zh" else brand.english_name,
                    "english_name": brand.english_name, "slug": brand.slug,
                    "path": _catalog_path(locale) + "?" + urlencode({"brand": brand.slug}),
                    "filter_only": True,
                })
            navigation_brands.sort(key=lambda row: (PRIORITY_BRANDS.index(row["english_name"]) if row["english_name"] in PRIORITY_BRANDS else len(PRIORITY_BRANDS), row["name"].casefold()))
        page["navigation"] = {
            "brands": navigation_brands,
            "box_sizes": sorted({o["box_size"] for p in stock for o in p["offers"] if o["in_stock"] and o["box_size"] is not None}),
            "has_sticks": any(o.get("sale_unit") == "stick" and o["in_stock"] for p in stock for o in p["offers"]),
        }
        base = page["path"].split("?", 1)[0]
        rows = rows_by_path[base]
        page["filter_options"] = {
            "brands": navigation_brands if page["kind"] == "home" else [],
            "box_sizes": sorted({o["box_size"] for p in rows for o in p["offers"] if o["box_size"] is not None}),
            "has_sticks": any(o.get("sale_unit") == "stick" and o["in_stock"] for p in rows for o in p["offers"]),
        }
        # Detail pages continue with actual same-brand stock, never synthetic recommendations.
        product = page.get("product")
        if product and product["brand_slug"]:
            page["products"] = [p for p in stock if p["brand_slug"] == product["brand_slug"] and p["id"] != product["id"]][:4]


def resolve_path(path: str, pages: dict[str, dict] | None = None) -> str:
    """Resolve a public URL to its current canonical path (including its slug)."""
    cleaned = _clean_path(urlsplit(path or "/").path)
    pages = pages if pages is not None else build_pages()
    if cleaned in pages:
        return cleaned
    # Product URLs retain the numeric ID as their stable identifier.
    match = re.fullmatch(r"(?P<prefix>/(?:ru|en))?/cigar/(?P<id>\d+)(?:/[^/]*)?/?", cleaned)
    if match:
        locale = (match.group("prefix") or "").strip("/") or "zh"
        for current_path, payload in pages.items():
            product = payload.get("product")
            if payload["locale"] == locale and product and str(product["id"]) == match.group("id"):
                return current_path
    return cleaned


def public_dependencies() -> dict:
    """Take a compact snapshot of dependencies whose revocation hides cached HTML."""
    return {
        "cigars": dict(Cigar.objects.filter(deleted_at__isnull=True).values_list("pk", "brand")),
        "withdrawn": set(ProductListing.objects.filter(withdrawn=True).values_list("cigar_id", flat=True)),
        "published": set(ProductListing.objects.filter(published=True, withdrawn=False).values_list("cigar_id", flat=True)),
        "translations": set(_published_translations()),
        "brand_slugs": dict(Brand.objects.values_list("english_name", "slug")),
        "details_verified": StoreSettings.objects.filter(pk=1, details_verified=True).exists(),
    }


def allowed_payload(payload: dict, dependencies: dict | None = None) -> bool:
    """Reject cached HTML as soon as any referenced content is revoked."""
    if not isinstance(payload, dict) or not payload.get("path"):
        return False
    locale = payload.get("locale")
    kind = payload.get("kind")
    if locale not in LOCALES or kind not in {"home", "brand", "product"}:
        return False
    dependencies = dependencies or public_dependencies()
    translations = dependencies["translations"]
    used_translations = payload.get("translation_dependencies")
    # Older artifacts cannot distinguish legacy text from revoked custom text.
    # Rebuild them rather than continuing to expose untracked reviewed content.
    if not isinstance(used_translations, list):
        return False
    for dependency in used_translations:
        if (not isinstance(dependency, list) or len(dependency) != 3
                or not all(isinstance(value, str) and value for value in dependency)
                or dependency[0] not in {"home", "brand", "product"}
                or dependency[2] not in LOCALES
                or tuple(dependency) not in translations):
            return False
    has_translation = lambda translation_kind, key, translation_locale: (
        translation_kind, str(key), translation_locale,
    ) in translations
    if kind == "home" and not has_translation("home", "home", locale):
        return False
    if locale != "zh":
        for brand_row in payload.get("brands") or []:
            if not has_translation("brand", brand_row.get("slug", ""), locale):
                return False
    for brand_row in payload.get("navigation", {}).get("brands", []):
        if brand_row.get("slug") not in dependencies["brand_slugs"].values():
            return False
        if locale != "zh" and not brand_row.get("filter_only") and not has_translation("brand", brand_row.get("slug", ""), locale):
            return False
    if kind == "brand":
        slug = payload.get("path", "").split("?")[0].rstrip("/").split("/")[-1]
        if slug not in dependencies["brand_slugs"].values():
            return False
        if locale != "zh" and not has_translation("brand", slug, locale):
            return False
        if locale != "zh" and not has_translation("home", "home", locale):
            return False
    products = list(payload.get("products") or [])
    if payload.get("product"):
        products.append(payload["product"])
    for product in products:
        cigar_id = product.get("id")
        brand_name = dependencies["cigars"].get(cigar_id)
        if cigar_id not in dependencies["cigars"] or cigar_id in dependencies["withdrawn"]:
            return False
        listing_is_live = cigar_id in dependencies["published"]
        if (product.get("offers") or product.get("availability") != "catalog") and not listing_is_live:
            return False
        if locale != "zh" and not has_translation("product", cigar_id, locale):
            return False
        if locale != "zh":
            brand_slug = dependencies["brand_slugs"].get(brand_name)
            if (not brand_slug
                    or not has_translation("brand", brand_slug, locale)
                    or not has_translation("home", "home", locale)):
                return False
    site = payload.get("site") or {}
    has_verified_store_data = any(site.get(key) for key in (
        "address", "phone", "wechat", "map_url", "photo", "points_of_sales", "hours",
    ))
    if has_verified_store_data and not dependencies["details_verified"]:
        return False
    if site.get("hours") and not has_translation("home", "home", locale):
        return False
    for alternate in [*(payload.get("alternates") or []), *(payload.get("browsing_alternates") or [])]:
        alternate_locale = alternate.get("locale")
        if alternate_locale == locale or alternate_locale not in LOCALES:
            continue
        if kind == "home" and not has_translation("home", "home", alternate_locale):
            return False
        if kind == "brand":
            slug = payload.get("path", "").split("?")[0].rstrip("/").split("/")[-1]
            if alternate_locale != "zh" and not has_translation("brand", slug, alternate_locale):
                return False
            if alternate_locale != "zh" and not has_translation("home", "home", alternate_locale):
                return False
        if kind == "product":
            product_id = payload.get("product", {}).get("id")
            if alternate_locale != "zh":
                brand_name = dependencies["cigars"].get(product_id)
                brand_slug = dependencies["brand_slugs"].get(brand_name)
                if (not has_translation("product", product_id, alternate_locale)
                        or not has_translation("home", "home", alternate_locale)
                        or not brand_slug
                        or not has_translation("brand", brand_slug, alternate_locale)):
                    return False
    return True


def normalize_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "").casefold()
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def search_products(query: str, locale: str = "zh", limit: int | None = 20,
                    pages: dict[str, dict] | None = None) -> list[dict]:
    """Search live public catalog names and aliases with token-OR matching."""
    locale = locale if locale in LOCALES else "zh"
    tokens = [token for token in re.split(r"\W+", normalize_search_text(query), flags=re.UNICODE) if token]
    if not tokens:
        return []
    pages = pages if pages is not None else build_pages()
    products = []
    for page in pages.values():
        if page["locale"] != locale:
            continue
        product = page.get("product")
        if product:
            products.append(product)
        products.extend(page.get("products", []))
    deduped = {product["id"]: product for product in products}
    cigar_rows = {
        cigar.pk: cigar
        for cigar in Cigar.objects.filter(pk__in=deduped, deleted_at__isnull=True)
    }
    all_translations = defaultdict(list)
    brand_names = {row.english_name: row.name for row in Brand.objects.all()}
    for row in StoreTranslation.objects.filter(kind="product", published=True):
        if all(value.strip() for value in (row.title, row.description, row.body)):
            try:
                all_translations[int(row.key)].append(row)
            except (TypeError, ValueError):
                continue
    scored = []
    for product in deduped.values():
        cigar = cigar_rows.get(product["id"])
        translated_aliases = []
        for translation in all_translations.get(product["id"], []):
            translated_aliases.extend([translation.title, *translation.aliases.split()])
        legacy_names = [cigar.name, cigar.english_name, cigar.brand, cigar.common_name, cigar.common_name_cn,
                        cigar.vitola, cigar.vitola_cn, brand_names.get(cigar.brand)] if cigar else []
        haystack = normalize_search_text(" ".join([
            product.get("name", ""), product.get("english_name", ""), product.get("brand", ""), product.get("vitola", ""),
            *product.get("aliases", []), *translated_aliases, *filter(None, legacy_names),
        ]))
        if any(token in haystack for token in tokens):
            scored.append((sum(token in haystack for token in tokens), product))
    scored.sort(key=lambda item: (-item[0], item[1]["name"].casefold(), item[1]["id"]))
    selected = scored if limit is None else scored[:max(1, min(int(limit), 100))]
    return [product for _, product in selected]


BROWSING_PARAMETERS = ("q", "brand", "box", "sort")


def browse_page(payload: dict, params, pages: dict[str, dict]) -> dict:
    """Filter the entire public shelf before paging; never only the first 24 cards."""
    base = payload["path"].split("?", 1)[0]
    rows = [product for page in pages.values()
            if page["path"].split("?", 1)[0] == base for product in page["products"]]
    rows = list({p["id"]: p for p in rows}.values())
    query = params.get("q", "").strip()
    brands = list(dict.fromkeys(params.getlist("brand")))
    boxes = list(dict.fromkeys(params.getlist("box")))
    sort = params.get("sort", "catalog")
    if sort not in {"catalog", "name", "length"}:
        sort = "catalog"
    if query:
        matching = {p["id"] for p in search_products(query, payload["locale"], limit=None, pages=pages)}
        rows = [p for p in rows if p["id"] in matching]
    if brands:
        rows = [p for p in rows if p["brand_slug"] in brands]
    if boxes:
        rows = [p for p in rows if any(
            (o.get("sale_unit") == "stick" and o["in_stock"] and "stick" in boxes)
            or (o["box_size"] is not None and str(o["box_size"]) in boxes)
            for o in p["offers"]
        )]
    if sort == "name":
        rows.sort(key=lambda p: (normalize_search_text(p["name"]), p["id"]))
    elif sort == "length":
        rows.sort(key=lambda p: (p["length"] is None, p["length"] or 0, normalize_search_text(p["name"]), p["id"]))
    try:
        number = max(1, int(params.get("page", "1")))
    except (TypeError, ValueError):
        number = 1
    _, pagination = _pagination(number, len(rows), base)
    if number != pagination["page"]:
        from django.http import Http404
        raise Http404
    pairs = [(key, value) for key in BROWSING_PARAMETERS for value in params.getlist(key) if value]
    def url(page_number):
        values = [*pairs, *([("page", page_number)] if page_number > 1 else [])]
        return base + ("?" + urlencode(values) if values else "")
    pagination["previous"] = url(number - 1) if number > 1 else None
    pagination["next"] = url(number + 1) if number < pagination["total_pages"] else None
    return {
        **payload,
        "products": rows[(number - 1) * PAGE_SIZE:number * PAGE_SIZE],
        "total_products": len(rows), "pagination": pagination,
        "filters": {"q": query, "brands": brands, "boxes": boxes, "sort": sort},
    }


def semantic_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
