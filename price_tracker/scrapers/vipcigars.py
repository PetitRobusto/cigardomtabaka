"""
VIP Cigars 爬虫 (vipcigars.com)
瑞士雪茄店，页面结构简单，无 Cloudflare 防护

URL 模式：
- 品牌页：https://www.vipcigars.com/cuban-cigars/{brand-slug}
- 产品卡片：<article> 元素

产品信息：
- 标题：h3 标签
- 价格：文本中包含如 "4'588.00 EUR"（瑞士千分位格式，用单引号）
- 库存：button 文字为 "Add to Cart"（有货）或 "Out of Stock"（售罄）
- 盒装规格：文本中有 "Box of 20"、"Box of 10"、"Cabinet of 25" 等

特殊规则：
- 无包装规格（box_size）的产品跳过（小雪茄/Club/Mini/Short 等）
- Special Bundle 产品跳过（商业捆绑包装，非标准产品）
"""
import re
import json
import logging
from typing import Optional

from . import register_scraper
from ..scraper import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)

BASE_URL = 'https://www.vipcigars.com'

# 品牌名 → URL slug 映射
BRAND_SLUGS = {
    'Bolívar': 'bolivar',
    'Cohiba': 'cohiba',
    'Cuaba': 'cuaba',
    'Diplomáticos': 'diplomaticos',
    'El Rey del Mundo': 'el-rey-del-mundo',
    'Fonseca': 'fonseca',
    'Guantanamera': 'guantanamera',
    'H. Upmann': 'h-upmann',
    'Hoyo de Monterrey': 'hoyo-de-monterrey',
    'José L. Piedra': 'jose-l-piedra',
    'Juan López': 'juan-lopez',
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
    'San Cristóbal': 'san-cristobal',
    'Sancho Panza': 'sancho-panza',
    'Trinidad': 'trinidad',
    'Vegas Robaina': 'vegas-robaina',
    'Vegueros': 'vegueros',
}


@register_scraper('vipcigars')
class VipCigarsScraper(BaseScraper):
    """VIP Cigars 爬虫 — 无需 Playwright，requests 直接抓取"""

    source_slug = 'vipcigars'

    async def scrape_catalog(self) -> list[ScrapedItem]:
        """抓取全站所有品牌"""
        import asyncio
        import httpx

        all_items = []
        async with httpx.AsyncClient(
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
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

        # Dedup by URL
        seen = set()
        unique = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)

        logger.info(f'VIP Cigars total: {len(unique)} unique products')
        return unique

    async def _scrape_brand(self, client, brand_name: str, slug: str) -> list[ScrapedItem]:
        """抓取单个品牌页"""
        url = f'{BASE_URL}/cuban-cigars/{slug}'
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return self._parse_html(resp.text, brand_name, url)
        except Exception as e:
            logger.error(f'{brand_name}: {e}')
            return []

    def _parse_html(self, html: str, brand_name: str, base_url: str) -> list[ScrapedItem]:
        """解析 HTML 提取产品信息"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        items = []

        for article in soup.find_all('article'):
            item = self._parse_article(article, brand_name, base_url)
            if item:
                items.append(item)

        return items

    def _parse_article(self, article, brand_name: str, base_url: str) -> Optional[ScrapedItem]:
        """解析单个产品卡片"""
        # 标题
        title_el = article.find('h3')
        if not title_el:
            return None
        title = title_el.get_text(strip=True)

        # 商品链接
        link_el = article.find('a', href=True)
        url = ''
        if link_el:
            href = link_el['href']
            url = href if href.startswith('http') else f'{BASE_URL}{href}'

        # 库存状态：通过 button 文字判断
        button = article.find('button')
        btn_text = button.get_text(strip=True).lower() if button else ''
        in_stock = 'add to cart' in btn_text

        # 提取盒装规格：Box of 20, Box of 10, Cabinet of 25, Pack of 5, Tin of 20 等
        box_size = None
        article_text = article.get_text(separator=' ', strip=True)
        size_match = re.search(r'(?:BOX|Cabinet|Pack|Tin)\s+OF\s+(\d+)', article_text, re.IGNORECASE)
        if size_match:
            box_size = int(size_match.group(1))
        
        # 没有包装规格 → 跳过（小雪茄/Club/Mini 等无包装信息的产品）
        if box_size is None:
            logger.debug(f'Skip {title}: no box size found')
            return None

        # Special Bundle → 跳过（商业捆绑包装，非标准产品）
        if 'special bundle' in title.lower():
            logger.debug(f'Skip {title}: special bundle')
            return None

        # 提取价格：格式如 4'588.00 EUR
        price_eur = None
        price_match = re.search(r"(\d[\d',.]+)\s*EUR", article_text)
        if price_match:
            price_str = price_match.group(1).replace("'", '').replace(',', '')
            try:
                price_eur = float(price_str)
            except ValueError:
                pass

        # 无价格 → 强制标记售罄
        if price_eur is None:
            in_stock = False

        # 去掉品牌前缀得到产品名
        name = title
        for prefix in [brand_name, brand_name.replace('á', 'a'), brand_name.replace('í', 'i')]:
            if name.lower().startswith(prefix.lower()):
                name = name[len(prefix):].strip()
                break

        full_name = f'{brand_name} {name}'

        return ScrapedItem(
            name=full_name,
            price=price_eur,
            currency='EUR',
            url=url,
            box_size=box_size,
            in_stock=in_stock,
            raw_data={
                'brand': brand_name,
                'product': name,
                'title_original': title,
                'button_text': btn_text,
            }
        )
