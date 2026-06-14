"""COH import adapters for Price Snapshot ingestion."""
import re
from typing import Iterable

from .scraper import ScrapedItem


COH_SLUG_BRAND_MAP = {
    'belinda': 'Belinda',
    'bolivar': 'Bolívar',
    'cohiba': 'Cohiba',
    'combinaciones': 'Combinaciones',
    'cuaba': 'Cuaba',
    'diplomaticos': 'Diplomáticos',
    'el-rey-del-mundo': 'El Rey del Mundo',
    'fonseca': 'Fonseca',
    'guantanamera': 'Guantanamera',
    'h.upmann': 'H. Upmann',
    'hoyo-de-monterrey': 'Hoyo de Monterrey',
    'jose-l.-piedra': 'José L. Piedra',
    'juan-lopez': 'Juan López',
    'la-flor-de-cano': 'La Flor de Cano',
    'la-gloria-cubana': 'La Gloria Cubana',
    'montecristo': 'Montecristo',
    'partagas': 'Partagás',
    'por-larranaga': 'Por Larrañaga',
    'punch': 'Punch',
    'quai-dorsay': "Quai d'Orsay",
    'quintero-y-hermano': 'Quintero',
    'rafael-gonzalez': 'Rafael González',
    'ramon-allones': 'Ramón Allones',
    'romeo-y-julieta': 'Romeo y Julieta',
    'saint-luis-rey': 'Saint Luis Rey',
    'san-cristobal-de-la-habana': 'San Cristóbal',
    'sancho-panza': 'Sancho Panza',
    'trinidad': 'Trinidad',
    'troya': 'Troya',
    'vegas-robaina': 'Vegas Robaina',
    'vegueros': 'Vegueros',
    'vintage': 'Vintage',
}


def brand_from_slug(slug: str) -> str:
    """Map COH URL/data slug to the canonical brand hint."""
    return COH_SLUG_BRAND_MAP.get(slug, slug.replace('-', ' ').title())


def clean_coh_name(name: str) -> str:
    """Clean a COH product name while preserving enough detail for matching."""
    name = str(name or '').strip()
    name = re.sub(r'\s*[-–]\s*\d{4}\s*$', '', name)
    name = re.sub(r'^\d+\s*Packs?-\s*', '', name)
    name = re.sub(r'\s+(C/P|A/T|LCDH|EL\s+\d{4}|RE\s+\w+(\s+\d{4})?)\s*$', '', name)
    name = re.sub(
        r'\s*(Travel Humidor|Gift Box|Humidor|Limited Edition|Year of the \w+|Anejados)\s*',
        '',
        name,
        flags=re.I,
    )
    return name.strip()


def parse_coh_box_size(box_info) -> int | None:
    """Parse COH box text such as '3x2 Box', '25 Box', or 'Single'."""
    if not box_info:
        return None
    text = str(box_info).strip()
    m = re.match(r'(\d+)(?:x(\d+))?\s*(?:Box|Pack|Bundle|Single)', text, re.I)
    if m:
        a, b = int(m.group(1)), m.group(2)
        return a * int(b) if b else a
    if re.search(r'\bSingle\b', text, re.I):
        return 1
    return None


def iter_coh_items(data: dict) -> tuple[list[ScrapedItem], dict[str, int]]:
    """Convert COH import payloads to ScrapedItem values for ingest_items()."""
    items: list[ScrapedItem] = []
    stats = {'total': 0, 'skipped_no_price': 0}

    for slug, products in data.items():
        brand = brand_from_slug(slug)
        for prod in _safe_products(products):
            stats['total'] += 1
            raw_name = prod.get('name') or prod.get('product') or ''
            product = clean_coh_name(raw_name)
            if prod.get('brand') and product:
                name = f"{prod['brand']} {product}"
                brand_hint = str(prod['brand']).strip()
            else:
                name = product
                brand_hint = brand

            price = prod.get('price')
            if price is None or price == '':
                stats['skipped_no_price'] += 1
                continue

            box_info = prod.get('box_info', prod.get('boxInfo', ''))
            items.append(ScrapedItem(
                name=name,
                price=price,
                currency=prod.get('currency') or 'USD',
                box_size=parse_coh_box_size(box_info),
                box_price=price,
                in_stock=True,
                raw_data={
                    'brand': brand_hint,
                    'coh_name': raw_name,
                    'product': prod.get('product', product),
                    'box_info': box_info,
                },
            ))

    return items, stats


def _safe_products(products: Iterable) -> Iterable[dict]:
    if not isinstance(products, list):
        return []
    return (product for product in products if isinstance(product, dict))
