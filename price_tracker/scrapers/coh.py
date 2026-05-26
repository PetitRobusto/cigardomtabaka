"""COH Cigars (cigarsofhabanos.com) 爬虫

网站结构：老式表格布局，产品页公开可见（无需登录看价格）。
URL 模式：https://www.cohcigars.com/cigars-{brand-slug}

产品格式（纯文本提取）：
    Cohiba - Behike BHK 52
    Length (in inches): 4.7
    Ring Gauge: 52
    No Discounts Apply
    10 Box     $ 2750.00

策略：
1. 遍历所有品牌 slug → 请求品牌页
2. 提取 innerText，按行解析产品条目
3. 正则提取：品名、长度、环径、盒装、价格
4. 名字匹配 Cigar 模型
"""
import re
import json
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from price_tracker.scraper import BaseScraper, ScrapedItem, match_cigar_by_name
from price_tracker.scrapers import register_scraper

logger = logging.getLogger(__name__)

BASE_URL = 'https://www.cohcigars.com'

# 品牌名 → COH slug 映射（27 个古巴品牌）
BRAND_SLUGS = {
    'Belinda': 'belinda',
    'Bolívar': 'bolivar',
    'Cohiba': 'cohiba',
    'Combinaciones': 'combinaciones',
    'Cuaba': 'cuaba',
    'Diplomáticos': 'diplomaticos',
    'El Rey del Mundo': 'el-rey-del-mundo',
    'Fonseca': 'fonseca',
    'Guantanamera': 'guantanamera',
    'H. Upmann': 'h.upmann',
    'Hoyo de Monterrey': 'hoyo-de-monterrey',
    'José L. Piedra': 'jose-l.-piedra',
    'Juan López': 'juan-lopez',
    'La Flor de Cano': 'la-flor-de-cano',
    'La Gloria Cubana': 'la-gloria-cubana',
    'Montecristo': 'montecristo',
    'Partagás': 'partagas',
    'Por Larrañaga': 'por-larranaga',
    'Punch': 'punch',
    'Quai d\'Orsay': 'quai-dorsay',
    'Quintero': 'quintero-y-hermano',
    'Rafael González': 'rafael-gonzalez',
    'Ramón Allones': 'ramon-allones',
    'Romeo y Julieta': 'romeo-y-julieta',
    'Saint Luis Rey': 'saint-luis-rey',
    'San Cristóbal': 'san-cristobal-de-la-habana',
    'Sancho Panza': 'sancho-panza',
    'Trinidad': 'trinidad',
    'Troya': 'troya',
    'Vegas Robaina': 'vegas-robaina',
    'Vegueros': 'vegueros',
}


def _parse_coh_page(html: str, brand_name: str, brand_hint: str) -> list[ScrapedItem]:
    """解析 COH 品牌页 HTML，提取产品列表"""
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n')
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Known COH brand names for validation (from menu sidebar)
    # Case-insensitive matching: normalize for comparison, strip accents
    import unicodedata
    def _normalize_brand(s: str) -> str:
        nfkd = unicodedata.normalize('NFKD', s)
        ascii_only = nfkd.encode('ascii', 'ignore').decode('ascii')
        return ascii_only.lower().replace('.', '').replace(' ', '').replace('-', '')

    known_brands_lower = {_normalize_brand(b) for b in BRAND_SLUGS.keys()}

    def _brand_matches(page_brand: str) -> bool:
        """Check if a brand from the page matches a known COH brand (case-insensitive, ignore accents/space/dot)"""
        return _normalize_brand(page_brand) in known_brands_lower

    # Also keep section headers that look like "Brand - Product" but aren't
    nav_patterns = re.compile(
        r'^(Specials|Limited Edition|Regional Release|'
        r'Boveda/Accessories|Custom Rolled|Damaged Cigar Clearance|'
        r'Special Promotion|Non-Cuban Cigars|Non-Cuban|Cuban Cigars'
        r'|Singles|10 Packs|5 Packs|Seleccion|Vintage'
        r'|Singles 6 Stick Min|Select Country|Home|About us|FAQ'
        r'|News|Contact Us|Terms & Cond)$', re.I
    )

    items = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip nav/sidebar lines
        if nav_patterns.match(line):
            i += 1
            continue

        # 匹配产品名行：支持 "Cohiba - Behike BHK 52" 或 "Montecristo No. 2"
        name_match = re.match(r'^([A-Za-zÀ-ÿ][\wÀ-ÿ\.\s\'&]+?)\s*-\s*(.+)$', line)

        if name_match:
            brand_from_line = name_match.group(1).strip()
            product_name = name_match.group(2).strip()

            # Only accept if the brand part is a known Cuban brand
            if not _brand_matches(brand_from_line):
                i += 1
                continue

            full_name = f'{brand_from_line} {product_name}'

            length_val = ''
            ring_val = ''
            box_info = ''
            price_str = ''

            i += 1
            while i < len(lines):
                nl = lines[i]
                if re.match(r'^([A-Za-zÀ-ÿ][\wÀ-ÿ\.\s\'&]+?)\s*-\s*.+$', nl):
                    break  # 下一个产品
                if 'You must be 18' in nl or 'HOME' == nl or 'FAQ' in nl:
                    break
                if re.match(r'Length.*inch', nl, re.I):
                    length_val = nl
                elif re.match(r'Ring Gauge', nl, re.I):
                    ring_val = nl
                elif re.search(r'(\d+)\s*(Box|Pack|Bundle|Single)', nl, re.I):
                    box_info = nl
                    # 提取价格
                    prices = re.findall(r'\$\s*([\d,]+\.?\d*)', nl)
                    if prices:
                        price_str = prices[-1]  # 取最后一个（打折后的实际价格）
                elif re.search(r'\$\s*[\d,]+', nl):
                    prices = re.findall(r'\$\s*([\d,]+\.?\d*)', nl)
                    if prices:
                        price_str = prices[-1]
                i += 1

            # 解析盒装数量
            box_size = None
            if box_info:
                # "25 Box" → 25, "3 Pack" → 3, "3x2 Box" → 6, "5x5 Box" → 25
                # "Single" (no leading digit) → 1
                m = re.match(r'(\d+)(?:x(\d+))?\s*(?:Box|Pack|Bundle|Single)', box_info, re.I)
                if m:
                    a = int(m.group(1))
                    b = m.group(2)
                    box_size = a * int(b) if b else a
                elif re.search(r'Single', box_info, re.I):
                    box_size = 1

            # 解析价格
            price = None
            if price_str:
                try:
                    price = float(price_str.replace(',', ''))
                except ValueError:
                    pass

            if full_name and price:
                items.append(ScrapedItem(
                    name=full_name,
                    price=price,
                    box_size=box_size,
                    box_price=price,
                    url=f'{BASE_URL}/cigars-{BRAND_SLUGS.get(brand_name, brand_name.lower().replace(" ", "-"))}',
                    in_stock=True,
                    raw_data={
                        'brand': brand_from_line,
                        'product': product_name,
                        'length': length_val,
                        'ring_gauge': ring_val,
                        'box_info': box_info,
                    },
                ))
        i += 1

    return items


@register_scraper('coh')
class COHCigarsScraper(BaseScraper):
    """
    COH Cigars 爬虫

    站点特征：
    - 老式表格布局，innerText 可完整提取
    - 无需登录看价格（！）
    - Cloudflare 有但似乎只护首页，品牌子页可直接 requests
    """

    def __init__(self, source):
        super().__init__(source)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    async def scrape_catalog(self) -> list[ScrapedItem]:
        all_items = []

        # Fetch home page first to warm up the session
        try:
            self.session.get(f'{BASE_URL}/home.aspx', timeout=30)
        except Exception:
            pass

        for brand_name, slug in BRAND_SLUGS.items():
            url = f'{BASE_URL}/cigars-{slug}'
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                items = _parse_coh_page(resp.text, brand_name, brand_name)
                logger.info(f'COH {brand_name}: {len(items)} products')
                all_items.extend(items)
            except Exception as e:
                logger.warning(f'COH {brand_name} failed: {e}')

        return all_items
