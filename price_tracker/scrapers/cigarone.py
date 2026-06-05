"""
CigarOne 爬虫 (cigarone.com)
瑞士雪茄店，自定义 PHP 站点（非 Shopify），无 Cloudflare 防护

URL 模式：
- 品牌页：https://www.cigarone.com/habanos-and-more-brands/{brand-slug}
- 产品行：.product-table 元素
- 产品详情：/habanos-and-more-brands/{brand}/{product}.html

产品信息（品牌列表页）：
- 品名：h2 > a 文本
- URL：h2 > a href
- 盒装规格：列文本 "Box of 20"
- 原价：<strike> 标签
- 折后价：.price-discounted span
- 币种：CHF
- 库存：.add-to-cart 按钮存在 = 有货

图片（详情页）：
- 大图：.product-unit-image-fullsize
- 缩略图：.product-unit-image-thumbnail
- 路径：/dist/img/catalog/products/card/{brand}-{product}_{n}.png

特殊规则：
- 只抓 /habanos-and-more-brands/ 下的产品（跳过 offers/combo/exclusive）
- 跳过 box_size=None 且 price=None 的空行
- 价格格式：瑞士千分位（4'310.00 → 4310.00）
"""
import re
import logging
from typing import Optional
from urllib.parse import urljoin

from . import register_scraper
from ..scraper import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)

BASE_URL = 'https://www.cigarone.com'

# 品牌名 → URL slug 映射（仅古巴品牌）
BRAND_SLUGS = {
    'Bolívar': 'bolivar',
    'Cohiba': 'cohiba',
    'Cuaba': 'cuaba',
    'Diplomáticos': 'diplomaticos',
    'El Rey del Mundo': 'el-rey-del-mundo',
    'Fonseca': 'fonseca',
    'H. Upmann': 'h-upmann',
    'Hoyo de Monterrey': 'hoyo-de-monterrey',
    'Juan López': 'juan-lopez',
    'José L. Piedra': 'jose-l-piedra',
    'La Flor de Cano': 'la-flor-de-cano',
    'La Gloria Cubana': 'la-gloria-cubana',
    'Montecristo': 'montecristo',
    'Partagás': 'partagas',
    'Por Larrañaga': 'por-larranaga',
    'Punch': 'punch',
    "Quai d'Orsay": 'quai-dorsay',
    'Quintero': 'quintero',
    'Rafael González': 'rafael-gonzalez',
    'Ramón Allones': 'ramon-allones',
    'Romeo y Julieta': 'romeo-y-julieta',
    'Saint Luis Rey': 'saint-luis-rey',
    'San Cristóbal': 'san-cristobal-de-la-habana',
    'Sancho Panza': 'sancho-panza',
    'Trinidad': 'trinidad',
    'Vegas Robaina': 'vegas-robaina',
    'Vegueros': 'vegueros',
}


def _parse_ch_price(text: str) -> Optional[float]:
    """解析瑞士价格格式：4'310.00 → 4310.0"""
    if not text:
        return None
    # 去除非数字字符（保留小数点）
    cleaned = text.replace("'", '').replace(',', '').replace('CHF', '').strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _extract_box_size(text: str) -> Optional[int]:
    """从 'Box of 20' / 'Cabinet of 25' 等文本提取支数"""
    m = re.search(r'(?:Box|Cabinet|Pack|Tin|Bundle)\s+of\s+(\d+)', text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


@register_scraper('cigarone')
class CigarOneScraper(BaseScraper):
    """CigarOne 爬虫 — httpx + BeautifulSoup"""

    source_slug = 'cigarone'

    async def scrape_catalog(self) -> list[ScrapedItem]:
        import asyncio
        import httpx

        all_items = []
        async with httpx.AsyncClient(
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            tasks = []
            for brand_name, slug in BRAND_SLUGS.items():
                tasks.append(self._scrape_brand(client, brand_name, slug))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for brand_name, result in zip(BRAND_SLUGS.keys(), results):
                if isinstance(result, Exception):
                    logger.error(f'{brand_name}: {result}')
                else:
                    all_items.extend(result)
                    logger.info(f'{brand_name}: {len(result)} products')

        # 去重：同 URL + 同 box_size 只保留有价格的那条
        seen = {}
        for item in all_items:
            key = (item.url, item.box_size)
            if key not in seen:
                seen[key] = item
            elif item.price is not None and seen[key].price is None:
                seen[key] = item

        unique = list(seen.values())
        logger.info(f'CigarOne total: {len(unique)} unique products (from {len(all_items)} raw rows)')
        return unique

    async def _scrape_brand(self, client, brand_name: str, slug: str) -> list[ScrapedItem]:
        url = f'{BASE_URL}/habanos-and-more-brands/{slug}'
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return self._parse_html(resp.text, brand_name, url)
        except Exception as e:
            logger.error(f'{brand_name}: {e}')
            return []

    def _parse_html(self, html: str, brand_name: str, base_url: str) -> list[ScrapedItem]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        items = []

        for row in soup.find_all(class_='product-table'):
            item = self._parse_row(row, brand_name)
            if item:
                items.append(item)

        return items

    def _parse_row(self, row, brand_name: str) -> Optional[ScrapedItem]:
        # 品名 + URL
        name_el = row.find('h2')
        if not name_el:
            return None
        link_el = name_el.find('a', href=True)
        if not link_el:
            return None

        title = link_el.get_text(strip=True)
        url = link_el['href']
        if not url.startswith('http'):
            url = urljoin(BASE_URL, url)

        # 只抓 /habanos-and-more-brands/ 的产品
        if '/habanos-and-more-brands/' not in url:
            logger.debug(f'Skip non-brand: {title} ({url})')
            return None

        # 提取所有列文本
        columns = row.find_all(class_='column')
        col_texts = [c.get_text(separator=' ', strip=True) for c in columns]

        # 盒装规格
        box_size = None
        for txt in col_texts:
            bs = _extract_box_size(txt)
            if bs:
                box_size = bs
                break

        # 价格提取
        price = None
        original_price = None
        strike_el = row.find('strike')
        if strike_el:
            original_price = _parse_ch_price(strike_el.get_text(strip=True))

        discount_el = row.find(class_='price-discounted')
        if discount_el:
            price = _parse_ch_price(discount_el.get_text(strip=True))

        # 如果 .price-discounted 没找到，尝试从 strong 中提取
        if price is None:
            strong_el = row.find('strong')
            if strong_el:
                text = strong_el.get_text(strip=True)
                # 取第一个价格数字
                for part in text.split():
                    p = _parse_ch_price(part)
                    if p:
                        price = p
                        break

        # 库存：有 .add-to-cart 按钮 = 有货
        has_cart = row.find(class_='add-to-cart') is not None

        # 无盒装数且无价格 → 跳过（空行/header行）
        if box_size is None and price is None:
            logger.debug(f'Skip empty row: {title}')
            return None

        # 构建完整品名
        name = f'{brand_name} {title}'

        # 提取图片 URL（从详情页，这里先放 raw_data）
        return ScrapedItem(
            name=name,
            price=price,
            original_price=original_price,
            currency='CHF',
            url=url,
            box_size=box_size,
            in_stock=has_cart,
            raw_data={
                'brand': brand_name,
                'product': title,
                'title_original': title,
            }
        )

    async def fetch_images(self, product_url: str) -> dict:
        """访问产品详情页提取图片 URL"""
        import httpx
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient(
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
            timeout=30.0,
        ) as client:
            try:
                resp = await client.get(product_url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f'fetch_images failed: {product_url}: {e}')
                return {}

        soup = BeautifulSoup(resp.text, 'html.parser')

        images = {}

        # 大图（主图）
        fullsize = soup.find(class_='product-unit-image-fullsize')
        if fullsize and fullsize.get('src'):
            images['fullsize'] = urljoin(BASE_URL, fullsize['src'])

        # 缩略图列表
        thumbnails = []
        for thumb in soup.find_all(class_='product-unit-image-thumbnail'):
            if thumb.get('src'):
                thumbnails.append(urljoin(BASE_URL, thumb['src']))
        if thumbnails:
            images['thumbnails'] = thumbnails

        # 尺子图
        ruler = soup.find(class_='product-stick-image')
        if ruler and ruler.get('src'):
            images['ruler'] = urljoin(BASE_URL, ruler['src'])

        return images
