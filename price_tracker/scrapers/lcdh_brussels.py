"""
LCDH Brussels 爬虫 (lacasadelhabano.brussels)

Shopify 网站，使用 Shopify AJAX API 直接获取结构化产品数据。
URL: https://lacasadelhabano.brussels

数据源: /collections/{handle}/products.json
- price: 实际成交价（折后价），欧元
- compare_at_price: 原价（划线价），null=无折扣
- tags: 品牌标签（第一个通常是品牌名）
- title: 品名 + 盒装数（如 "COHIBA PANETELAS /25"）
"""

import re
import logging
from typing import Optional

from . import register_scraper
from ..scraper import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)

BASE_URL = 'https://lacasadelhabano.brussels'

# 雪茄相关 collection（排除 BOOKS/HUMIDORS）
CIGAR_COLLECTIONS = [
    'classic-lines',
    'aged',
    'lcdh',
    'limited-edition',
    'regional-edition',
    'frontpage',        # GRAN RESERVA
    'chinese-new-year-series',
    'jars',
]

# 品牌名映射（从 tags/URL提取 → 标准品牌名）
TAG_BRAND_MAP = {
    'COHIBA': 'Cohiba',
    'CUABA': 'Cuaba',
    'PARTAGAS': 'Partagás',
    'TRINIDAD': 'Trinidad',
    'DIPLOMATICOS': 'Diplomáticos',
    'ROMEO Y JULIETA': 'Romeo y Julieta',
    'ROMEO': 'Romeo y Julieta',
    'BOLIVAR': 'Bolívar',
    'BOLÍVAR': 'Bolívar',
    'MONTECRISTO': 'Montecristo',
    'H. UPMANN': 'H. Upmann',
    'HOYO DE MONTERREY': 'Hoyo de Monterrey',
    'PUNCH': 'Punch',
    'VEGAS ROBAINA': 'Vegas Robaina',
    'SAN CRISTOBAL': 'San Cristóbal',
    'JUAN LOPEZ': 'Juan López',
    'POR LARRANAGA': 'Por Larrañaga',
    'RAFAEL GONZALEZ': 'Rafael González',
    'RAMON ALLONES': 'Ramón Allones',
    'QUAI DORSAY': "Quai d'Orsay",
    'EL REY DEL MUNDO': 'El Rey del Mundo',
    'LA GLORIA CUBANA': 'La Gloria Cubana',
    'FONSECA': 'Fonseca',
    'SANCHO PANZA': 'Sancho Panza',
    'VEGUEROS': 'Vegueros',
    'QUINTERO': 'Quintero',
}


@register_scraper('lcdh_brussels')
class LcdhBrusselsScraper(BaseScraper):
    """LCDH Brussels — Shopify, 通过 AJAX API 抓取"""

    source_slug = 'lcdh_brussels'

    async def scrape_catalog(self) -> list[ScrapedItem]:
        """抓取全站雪茄产品 — 使用 Playwright 浏览器（需要年龄验证 cookie）"""
        # 注意：httpx API 不携带年龄验证 cookie，导致所有产品显示缺货
        # 改为 Playwright 浏览器模式
        from playwright.async_api import async_playwright
        
        seen_handles = set()
        all_items = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # 先过年龄验证
            await page.goto(f'{BASE_URL}/zh/collections/classic-lines', timeout=30000)
            # 点击 "I am 18 or older"
            try:
                btn = page.locator('button:has-text("18")').first
                await btn.click(timeout=5000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass  # 可能已经过了
            
            for col_handle in CIGAR_COLLECTIONS:
                try:
                    # 用浏览器 fetch API 拿到 collection 数据（带 cookie）
                    products = await page.evaluate(f'''
                        async () => {{
                            const resp = await fetch('/collections/{col_handle}/products.json?limit=250');
                            const data = await resp.json();
                            return data.products || [];
                        }}
                    ''')
                except Exception as e:
                    logger.error(f'{col_handle}: {e}')
                    continue
                
                logger.info(f'{col_handle}: {len(products)} products')
                
                for prod in products:
                    handle = prod.get('handle', '')
                    if handle in seen_handles:
                        continue
                    seen_handles.add(handle)
                    
                    item = self._parse_product(prod)
                    if item:
                        all_items.append(item)
            
            await browser.close()
        
        logger.info(f'LCDH Brussels total: {len(all_items)} unique products')
        return all_items

    def _parse_product(self, prod: dict) -> Optional[ScrapedItem]:
        """解析单个 Shopify product → ScrapedItem"""
        title = (prod.get('title') or '').strip()
        if not title:
            return None

        tags = [t.strip() for t in prod.get('tags', [])]
        variants = prod.get('variants', [])
        if not variants:
            return None

        # 使用第一个 variant
        variant = variants[0]
        price_str = variant.get('price')
        compare_at = variant.get('compare_at_price')
        available = variant.get('available', False)
        in_stock = bool(available)  # 强制转 bool（Playwright evaluate 可能丢类型）
        variant_title = variant.get('title', '')

        if price_str is None:
            return None

        try:
            actual_price = float(price_str)  # 实际成交价
        except (ValueError, TypeError):
            return None

        original_price = None
        if compare_at:
            try:
                original_price = float(compare_at)
            except (ValueError, TypeError):
                pass

        # 库存状态（已在上方从 variant.available 设置）
        # 提取品牌
        brand = self._extract_brand(title, tags)

        # 提取盒装数
        box_size = self._extract_box_size(title, variant_title, tags)

        # 没有包装规格 → 不在此跳过，由 save_items 全局推断逻辑处理
        # （查历史数据：唯一规格自动补，多规格跳过）

        # 使用原始标题作为品名（matcher 会处理品牌前缀和备款剥离）
        name = title

        # URL
        handle = prod.get('handle', '')
        url = f'{BASE_URL}/products/{handle}' if handle else ''

        # 跳过 sampler/festival set/assortment
        if self._is_sampler(title, tags):
            logger.debug(f'Skip sampler: {title}')
            return None

        return ScrapedItem(
            name=name,
            price=actual_price,
            original_price=original_price,
            box_size=box_size,
            url=url,
            in_stock=in_stock,
            currency='EUR',
            raw_data={
                'title_original': title,
                'brand': brand,
                'tags': tags,
                'variant_title': variant_title,
                'has_discount': compare_at is not None and float(compare_at) > 0,
            },
        )

    def _extract_brand(self, title: str, tags: list[str]) -> str:
        """从标题和标签提取品牌名"""
        # 方法1: 从 tags 中匹配已知品牌
        title_upper = title.upper()
        for tag in tags:
            tag_upper = tag.strip().upper()
            if tag_upper in TAG_BRAND_MAP:
                return TAG_BRAND_MAP[tag_upper]

        # 方法2: 从标题中匹配已知品牌
        for tag_key, brand_name in sorted(TAG_BRAND_MAP.items(), key=lambda x: -len(x[0])):
            if tag_key in title_upper:
                return brand_name

        # 方法3: 从标题中提取第一个词作为品牌名
        brand = title.upper().split()[0] if title else ''
        return TAG_BRAND_MAP.get(brand, brand.title())

    def _extract_box_size(self, title: str, variant_title: str, tags: list[str]) -> Optional[int]:
        """提取盒装支数"""
        # 从标题提取 /25, /10, x25, Box of 12 等
        patterns = [
            r'/(\d+)\b',               # /25
            r'\bx(\d+)\b',             # x25
            r'BOX\s+OF\s+(\d+)',       # BOX OF 12
            r'(\d+)\s*BOX\b',          # 25 BOX
            r'CABINET\s+OF\s+(\d+)',   # CABINET OF 25
            r'(\d+)\s*只',             # 25只
            r'(\d+)\s*支',             # 25支
            r'\b(\d+)\s*PACK\b',       # 3 PACK
            r'PACK\s*OF\s*(\d+)',      # PACK OF 3
        ]
        for pat in patterns:
            m = re.search(pat, title, re.IGNORECASE)
            if m:
                size = int(m.group(1))
                if 1 <= size <= 100:
                    return size

        # 从 tags 提取可靠盒装信息
        for tag in tags:
            tag_lower = tag.strip().lower()
            m = re.search(r'(\d+)\s*(box|cabinet|pack)', tag_lower)
            if m:
                size = int(m.group(1))
                if 1 <= size <= 100:
                    return size

        return None

    def _build_name(self, title: str, brand: str) -> str:
        """构建用于匹配的产品名"""
        name = title.strip()
        # 去掉年份后缀
        name = re.sub(r'\s+\d{4}\s*$', '', name)
        # 去掉盒装数 "/25", "/10" 等（任何位置）
        name = re.sub(r'\s*/\d+\b', '', name)
        # 去掉品牌前缀
        if brand:
            brand_upper = brand.upper()
            if name.upper().startswith(brand_upper):
                name = name[len(brand):].strip()
        # 去掉通用后缀
        name = re.sub(r'\s+(AGED|YEAR|SEALED\s+BOX|LIMITED\s+EDITION|GRAN\s+RESERVA|LCDH)\s*$', '', name, flags=re.IGNORECASE)
        return name.strip()

    def _is_sampler(self, title: str, tags: list[str]) -> bool:
        """判断是否为 sampler/节日套装/assortment"""
        title_upper = title.upper()
        sampler_keywords = [
            'FESTIVAL SET', 'SAMPLER', 'ASSORTMENT', 'SELECTION',
            'VARIETY', 'MIX', 'TASTER', 'GIFT SET',
        ]
        for kw in sampler_keywords:
            if kw in title_upper:
                return True
        # Jars/陶瓷罐 也是特殊产品
        for tag in tags:
            if tag.upper() in ('JAR', 'CERAMIC JAR', 'HUMIDOR'):
                return True
        return False
