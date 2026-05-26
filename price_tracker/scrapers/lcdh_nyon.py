"""
LCDH Nyon 爬虫 (la-casa-del-habano-nyon.com)
瑞士雪茄店，WooCommerce + Flatsome主题
Cloudflare防护 → 必须通过已认证页面用 fetch() 爬取
"""
import re, json, logging
from typing import Optional

from . import register_scraper
from ..scraper import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)

BASE_URL = 'https://la-casa-del-habano-nyon.com'

# 所有古巴雪茄品牌（category slug → brand name）
BRAND_CATEGORIES = {
    'bolivar': 'Bolívar',
    'cohiba': 'Cohiba',
    'cuaba': 'Cuaba',
    'diplomaticos': 'Diplomáticos',
    'el-rey-del-mundo': 'El Rey del Mundo',
    'fonseca': 'Fonseca',
    'guantanamera': 'Guantanamera',
    'h-upmann': 'H. Upmann',
    'hoyo-de-monterrey': 'Hoyo de Monterrey',
    'jose-l-piedra': 'José L. Piedra',
    'juan-lopez': 'Juan López',
    'la-flor-de-cano': 'La Flor de Cano',
    'la-gloria-cubana': 'La Gloria Cubana',
    'montecristo': 'Montecristo',
    'partagas': 'Partagás',
    'por-larranaga': 'Por Larrañaga',
    'punch': 'Punch',
    'quai-dorsay': 'Quai d\'Orsay',
    'quintero': 'Quintero',
    'rafael-gonzalez': 'Rafael González',
    'ramon-allones': 'Ramón Allones',
    'romeo-y-julieta': 'Romeo y Julieta',
    'saint-luis-rey': 'Saint Luis Rey',
    'san-cristobal-de-la-habana': 'San Cristóbal de la Habana',
    'sancho-panza': 'Sancho Panza',
    'trinidad': 'Trinidad',
    'vegas-robaina': 'Vegas Robaina',
    'vegueros': 'Vegueros',
}


@register_scraper('lcdh_nyon')
class LCDHNyonScraper(BaseScraper):
    """LCDH Nyon 爬虫 — 需要 Playwright browser 先过 Cloudflare"""
    
    source_slug = 'lcdh_nyon'
    
    def __init__(self, source, browser_page=None):
        super().__init__(source)
        self._page = browser_page
    
    def scrape(self) -> list[ScrapedItem]:
        """从 Playwright page context 抓取所有产品"""
        if not self._page:
            raise RuntimeError('LCDHNyonScraper requires a Playwright browser page')
        
        all_items = []
        for cat_slug, brand_name in BRAND_CATEGORIES.items():
            url = f'{BASE_URL}/en/product-category/cigares-cubains/{cat_slug}/'
            try:
                items = self._scrape_brand(brand_name, cat_slug)
                all_items.extend(items)
                logger.info(f'  {brand_name}: {len(items)} products')
            except Exception as e:
                logger.error(f'  {brand_name}: {e}')
        
        # 去重（按URL）
        seen = set()
        unique = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        
        return unique
    
    def _scrape_brand(self, brand_name: str, cat_slug: str) -> list[ScrapedItem]:
        """抓取单个品牌的所有产品"""
        result = self._page.evaluate(f'''
            async () => {{
                const resp = await fetch('/en/product-category/cigares-cubains/{cat_slug}/');
                const html = await resp.text();
                const div = document.createElement('div');
                div.innerHTML = html;
                
                const products = [];
                const cards = div.querySelectorAll('.product-small, li.product');
                
                cards.forEach(card => {{
                    const titleEl = card.querySelector('.product-title a, .woocommerce-loop-product__title');
                    const priceEl = card.querySelector('.price .woocommerce-Price-amount, .price');
                    const linkEl = card.querySelector('a[href*="/boutique/"]');
                    const imgEl = card.querySelector('img');
                    const badgeEl = card.querySelector('.out-of-stock, .badge-inner');
                    
                    if (!titleEl) return;
                    
                    const title = titleEl.textContent.trim();
                    const price = priceEl?.textContent?.trim() || '';
                    const url = linkEl?.getAttribute('href') || '';
                    const img = imgEl?.getAttribute('src') || '';
                    const badge = badgeEl?.textContent?.trim() || '';
                    const inStock = !badge.includes('out of stock') && !badge.includes('Out of stock');
                    
                    products.push({{
                        title, price, url, img, badge, inStock
                    }});
                }});
                
                return JSON.stringify(products);
            }}
        ''')
        
        data = json.loads(result)
        items = []
        for p in data:
            item = self._parse_product(p, brand_name)
            if item:
                items.append(item)
        
        return items
    
    def _parse_product(self, raw: dict, brand: str) -> Optional[ScrapedItem]:
        """解析单个产品"""
        title = raw.get('title', '')
        price_str = raw.get('price', '')
        url = raw.get('url', '')
        in_stock = raw.get('inStock', True)
        
        if not title or not price_str:
            return None
        
        # 解析标题: "Bolívar Regentes Edición Limitada 2021 (25)"
        # 去掉品牌前缀
        name = title
        for prefix in [brand, brand.replace('á','a'), brand.replace('í','i')]:
            if name.lower().startswith(prefix.lower()):
                name = name[len(prefix):].strip()
                break
        
        # 提取盒装支数
        box_size = None
        m = re.search(r'\((\d+)\)', name)
        if m:
            box_size = int(m.group(1))
            name = re.sub(r'\s*\(\d+\)', '', name).strip()
        
        # 解析价格: "Swiss franc 1,350.00"
        price_chf = None
        m = re.search(r'[\d,]+\.?\d*', price_str.replace("'", ''))
        if m:
            price_chf = float(m.group().replace(',', ''))
        
        # 完整原始品名（用于匹配）
        full_name = f'{brand} {name}'
        
        return ScrapedItem(
            name=full_name,
            price=price_chf,
            currency='CHF',
            url=url,
            box_size=box_size,
            in_stock=in_stock,
            raw_data={
                'brand': brand,
                'product': name,
                'title_original': title,
                'price_original': price_str,
            }
        )
