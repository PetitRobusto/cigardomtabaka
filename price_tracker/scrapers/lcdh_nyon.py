"""
LCDH Nyon 爬虫 (la-casa-del-habano-nyon.com)
瑞士雪茄店，WooCommerce + Flatsome主题
Cloudflare防护 → 独立 headless Chromium + stealth 绕过
"""
import re, json, logging
from typing import Optional

from . import register_scraper
from ..scraper import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)

BASE_URL = 'https://la-casa-del-habano-nyon.com'

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
    'san-cristobal': 'San Cristóbal',
    'sancho-panza': 'Sancho Panza',
    'trinidad': 'Trinidad',
    'vegas-robaina': 'Vegas Robaina',
    'vegueros': 'Vegueros',
}


@register_scraper('lcdh_nyon')
class LCDHNyonScraper(BaseScraper):
    """LCDH Nyon 爬虫 — 独立 Chromium + stealth + 批处理绕过 Cloudflare"""
    
    source_slug = 'lcdh_nyon'
    
    async def scrape_catalog(self) -> list[ScrapedItem]:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
        
        all_items = []
        brand_list = list(BRAND_CATEGORIES.items())
        batch_size = 10
        
        async with async_playwright() as p:  # 单次启动 driver
            for batch_start in range(0, len(brand_list), batch_size):
                batch = brand_list[batch_start:batch_start + batch_size]
                
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
                )
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                               '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US'
                )
                page = await context.new_page()
                stealth = Stealth()
                await stealth.apply_stealth_async(page)
                
                try:
                    await page.goto(f'{BASE_URL}/en/?currency=CHF',
                                   wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(3000)
                    
                    body = await page.locator('body').inner_text()
                    if '安全验证' in body or 'challenge' in body.lower():
                        logger.warning(f'Nyon CF 封锁 (batch {batch_start//batch_size+1})')
                        continue
                    
                    await page.evaluate('''() => {
                        document.cookie = "woocs=CHF;path=/;max-age=86400";
                        document.cookie = "currency=CHF;path=/;max-age=86400";
                    }''')
                    
                    for cat_slug, brand_name in batch:
                        try:
                            items = await self._scrape_brand(page, brand_name, cat_slug)
                            all_items.extend(items)
                            logger.info(f'  {brand_name}: {len(items)} products')
                        except Exception as e:
                            logger.warning(f'  {brand_name}: {e}')
                    
                finally:
                    try:
                        await context.close()
                    except Exception:
                        pass
                    try:
                        await browser.close()
                    except Exception:
                        pass
        
        # 去重
        seen = set()
        unique = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        
        return unique
    
    async def _scrape_brand(self, page, brand_name: str, cat_slug: str) -> list[ScrapedItem]:
        """用 fetch() 抓取单个品牌"""
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
                    const cardClass = (card.className || '').toLowerCase();
                    const oosLabel = card.querySelector('.out-of-stock-label');
                    const oosBadgeText = (oosLabel?.textContent || '').trim().toLowerCase();
                    const addToCartEl = card.querySelector('.add_to_cart_button, .add-to-cart-button');
                    const cartText = (addToCartEl?.textContent || '').trim().toLowerCase();
                    const isOOS = cardClass.includes('out-of-stock') || cardClass.includes('outofstock')
                        || oosBadgeText.includes('rupture') || oosBadgeText.includes('out of stock')
                        || (cartText && !cartText.includes('add to cart') && !cartText.includes('select option'));
                    if (!titleEl) return;
                    const delAmount = priceEl?.querySelector('del .woocommerce-Price-amount, del .amount');
                    const insAmount = priceEl?.querySelector('ins .woocommerce-Price-amount, ins .amount');
                    const normalAmount = priceEl?.querySelector('.woocommerce-Price-amount, .amount');
                    const priceText = (delAmount && insAmount) ? insAmount.textContent.trim() : (normalAmount?.textContent?.trim() || priceEl?.textContent?.trim() || '');
                    const origPriceText = delAmount ? delAmount.textContent.trim() : '';
                    products.push({{
                        title: titleEl.textContent.trim(),
                        price: priceText,
                        originalPrice: origPriceText,
                        url: linkEl?.getAttribute('href') || '',
                        badge: oosLabel?.textContent?.trim() || (isOOS ? 'Out of stock' : ''),
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
    
    def _parse_product(self, raw: dict, brand: str) -> Optional[ScrapedItem]:
        """解析单个产品"""
        title = raw.get('title', '')
        price_str = raw.get('price', '')
        url = raw.get('url', '')
        in_stock = raw.get('inStock', True)
        
        if not title:
            return None
        if not price_str:
            in_stock = False
        
        # 去掉品牌前缀
        name = title
        for prefix in [brand, brand.replace('á','a'), brand.replace('í','i')]:
            if name.lower().startswith(prefix.lower()):
                name = name[len(prefix):].strip()
                break
        
        # 提取盒装支数
        box_size = None
        m = re.search(r'\((\d+)\s*[×xX]\s*(\d+)\)', name)
        if m:
            box_size = int(m.group(1)) * int(m.group(2))
            name = re.sub(r'\s*\(\d+\s*[×xX]\s*\d+\)', '', name).strip()
        else:
            m = re.search(r'\((\d+)\)', name)
            if m:
                box_size = int(m.group(1))
                name = re.sub(r'\s*\(\d+\)', '', name).strip()
        
        # 解析价格 + 货币检测
        price_chf = None
        detected_currency = 'CHF'
        if '€' in price_str or 'EUR' in price_str.upper():
            detected_currency = 'EUR'
        elif 'CHF' in price_str.upper() or 'swiss' in price_str.lower() or 'franc' in price_str.lower():
            detected_currency = 'CHF'
        
        # 提取原价（折扣时的划线价）
        orig_price_chf = None
        orig_price_str = raw.get('originalPrice', '')
        if orig_price_str:
            m_orig = re.search(r'[\d,]+\.?\d*', orig_price_str.replace("'", ''))
            if m_orig:
                orig_price_chf = float(m_orig.group().replace(',', ''))
        
        m_price = re.search(r'[\d,]+\.?\d*', price_str.replace("'", ''))
        if m_price:
            raw_price = float(m_price.group().replace(',', ''))
            if detected_currency == 'EUR':
                from price_tracker.models import ExchangeRate
                eur_rate = ExchangeRate.get_rate('EUR')
                chf_rate = ExchangeRate.get_rate('CHF')
                if eur_rate and chf_rate:
                    price_chf = round(raw_price * eur_rate / chf_rate, 2)
                else:
                    price_chf = round(raw_price * 1.10, 2)
            else:
                price_chf = raw_price
        
        full_name = f'{brand} {name}'
        
        return ScrapedItem(
            name=full_name,
            price=price_chf,
            original_price=orig_price_chf,
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
