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
    
    async def scrape_catalog(self) -> list[ScrapedItem]:
        """独立运行：启动 Playwright + stealth，抓取全站"""
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US'
            )
            page = await context.new_page()
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            
            # Load homepage to pass Cloudflare
            await page.goto(f'{BASE_URL}/en/', wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(8000)
            
            # Use fetch() to scrape all brands
            all_items = []
            for cat_slug, brand_name in BRAND_CATEGORIES.items():
                try:
                    items = await self._scrape_brand_async(page, brand_name, cat_slug)
                    all_items.extend(items)
                    logger.info(f'  {brand_name}: {len(items)} products')
                except Exception as e:
                    logger.error(f'  {brand_name}: {e}')
            
            await browser.close()
        
        # Dedup
        seen = set()
        unique = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        
        return unique
    
    async def _scrape_brand_async(self, page, brand_name: str, cat_slug: str) -> list[ScrapedItem]:
        """Async version: 用 fetch() 抓取单个品牌"""
        try:
            result = await page.evaluate(f'''
                async () => {{
                    const resp = await fetch('/en/product-category/cigares-cubains/{cat_slug}/');
                    const html = await resp.text();
                    const div = document.createElement('div');
                    div.innerHTML = html;
                    const products = [];
                    div.querySelectorAll('.product-small, li.product').forEach(card => {{
                        const titleEl = card.querySelector('.product-title a, .woocommerce-loop-product__title');
                        const priceEl = card.querySelector('.price');
                        const linkEl = card.querySelector('a[href*="/boutique/"]');
                        const badgeEl = card.querySelector('.out-of-stock, .badge-inner');
                        if (!titleEl) return;
                        const badgeText = (badgeEl?.textContent || '').trim().toLowerCase();
                        const isOOS = badgeText.includes('out of stock') || badgeText.includes('rupture de stock');
                        products.push({{
                            title: titleEl.textContent.trim(),
                            price: priceEl?.textContent?.trim() || '',
                            url: linkEl?.getAttribute('href') || '',
                            badge: badgeEl?.textContent?.trim() || '',
                            inStock: !isOOS
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
        except Exception as e:
            logger.error(f'{brand_name}: {e}')
            return []
    
    def _parse_product(self, raw: dict, brand: str) -> Optional[ScrapedItem]:
        """解析单个产品（含售罄产品）"""
        title = raw.get('title', '')
        price_str = raw.get('price', '')
        url = raw.get('url', '')
        in_stock = raw.get('inStock', True)
        
        if not title:
            return None
        
        # 无价格 → 强制标记售罄
        if not price_str:
            in_stock = False
        
        # 解析标题: "Bolívar Regentes Edición Limitada 2021 (25)"
        # 去掉品牌前缀
        name = title
        for prefix in [brand, brand.replace('á','a'), brand.replace('í','i')]:
            if name.lower().startswith(prefix.lower()):
                name = name[len(prefix):].strip()
                break
        
        # 提取盒装支数: (25) or (5×20) or (5 x 20)
        box_size = None
        # 先试 (5×20) / (5 x 20) 格式
        m = re.search(r'\((\d+)\s*[×xX]\s*(\d+)\)', name)
        if m:
            box_size = int(m.group(1)) * int(m.group(2))
            name = re.sub(r'\s*\(\d+\s*[×xX]\s*\d+\)', '', name).strip()
        else:
            # 单数字格式 (25)
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
