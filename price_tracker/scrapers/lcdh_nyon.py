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
NYON_EUR_TO_CHF_RATE = 0.9009009009


def _detect_display_currency(price_text: str) -> str:
    text = (price_text or '').lower()
    if '€' in text or 'eur' in text:
        return 'EUR'
    if 'chf' in text or 'swiss' in text or 'franc' in text:
        return 'CHF'
    return 'CHF'


def _parse_money(price_text: str) -> Optional[float]:
    match = re.search(r'[\d,]+\.?\d*', (price_text or '').replace("'", ''))
    if not match:
        return None
    return float(match.group().replace(',', ''))


def _canonicalize_nyon_price(amount: Optional[float], display_currency: str) -> Optional[float]:
    if amount is None:
        return None
    if display_currency == 'EUR':
        return round(amount * NYON_EUR_TO_CHF_RATE, 2)
    return amount



def _product_cards_js(root_expr: str) -> str:
    return f'''
                const products = [];
                {root_expr}.querySelectorAll('.product-small, li.product').forEach(card => {{
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
    '''


def _brand_parse_script() -> str:
    return f'''
            () => {{
{_product_cards_js('document')}
                return JSON.stringify(products);
            }}
        '''




def _nyon_delay_ms(index: int) -> int:
    return 15000 + (index % 5) * 3000


def _brand_parse_from_html_script(cat_slug: str) -> str:
    if not re.fullmatch(r'[a-z0-9-]+', cat_slug):
        raise ValueError('invalid Nyon category slug')
    category_path = json.dumps(f'/en/product-category/cigares-cubains/{cat_slug}/')
    return f'''
            async () => {{
                const resp = await fetch({category_path});
                const html = await resp.text();
                const div = document.createElement('div');
                div.innerHTML = html;
{_product_cards_js('div')}
                return JSON.stringify({{
                    status: resp.status,
                    title: div.querySelector('title')?.textContent || '',
                    bodyHead: (div.textContent || '').slice(0, 800),
                    count: products.length,
                    products
                }});
            }}
        '''


def _is_blocked_response(payload: dict) -> bool:
    status = payload.get('status')
    title = str(payload.get('title') or '').lower()
    body_head = str(payload.get('bodyHead') or '').lower()
    if status == 429:
        return True
    blocked_text = f'{title} {body_head}'
    return (
        '429' in blocked_text
        or 'too many requests' in blocked_text
        or 'just a moment' in blocked_text
        or 'security verification' in blocked_text
        or 'challenge' in blocked_text
    )

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
    """LCDH Nyon 爬虫 — 独立 Chromium + stealth 绕过 Cloudflare"""
    
    source_slug = 'lcdh_nyon'
    
    async def scrape_catalog(self) -> list[ScrapedItem]:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        all_items = []
        brand_list = list(BRAND_CATEGORIES.items())

        stealth = Stealth(
            navigator_webdriver=True,
            navigator_plugins=True,
            navigator_languages=True,
            navigator_platform=True,
            navigator_vendor=True,
            webgl_vendor=True,
            hairline=True,
            sec_ch_ua=True,
            chrome_app=True,
            chrome_csi=True,
            chrome_load_times=True,
            iframe_content_window=True,
            media_codecs=True,
            navigator_hardware_concurrency=True,
            navigator_permissions=True,
            navigator_user_agent_data=True,
            error_prototype=True,
            navigator_languages_override=('en-US', 'en'),
            navigator_platform_override='Win32',
            navigator_user_agent_override=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
            ),
            navigator_vendor_override='Google Inc.',
            webgl_vendor_override='Intel Inc.',
            webgl_renderer_override='Intel Iris OpenGL Engine',
        )

        async with stealth.use_async(async_playwright()) as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                      '--disable-blink-features=AutomationControlled',
                      '--disable-features=AutomationControlled,EnableAutomation'],
            )
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                               '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                )

                page = await context.new_page()
                await page.goto(f'{BASE_URL}/en/',
                               wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(3000)

                body = await page.locator('body').inner_text()
                if '429' in body or 'too many requests' in body.lower():
                    raise RuntimeError('Nyon rate limited on initial page (429)')
                if '安全验证' in body or 'challenge' in body.lower() or 'security verification' in body.lower():
                    logger.warning('Nyon CF 封锁')
                    return []

                await page.evaluate('''() => {
                    document.cookie = "woocs=CHF;path=/;max-age=86400";
                    document.cookie = "currency=CHF;path=/;max-age=86400";
                }''')

                # 首页后短暂冷却
                await page.wait_for_timeout(5000)

                for index, (cat_slug, brand_name) in enumerate(brand_list):
                    try:
                        items = await self._scrape_brand(page, brand_name, cat_slug)
                        all_items.extend(items)
                        logger.info(f'  {brand_name}: {len(items)} products')
                        if index < len(brand_list) - 1:
                            await page.wait_for_timeout(_nyon_delay_ms(index))
                    except Exception as e:
                        err_msg = str(e)
                        if 'rate limited' in err_msg.lower() or '429' in err_msg or 'cloudflare' in err_msg.lower():
                            raise RuntimeError(err_msg) from e
                        logger.warning(f'  {brand_name}: {err_msg[:80]}')

            finally:
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass

        if not all_items:
            raise RuntimeError('Nyon returned no products; likely blocked or rate limited')

        seen = set()
        unique = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)

        return unique

    async def _scrape_brand(self, page, brand_name: str, cat_slug: str) -> list[ScrapedItem]:
        """Fetch brand page via JS fetch() from already-CF-authenticated page context."""
        result = await page.evaluate(_brand_parse_from_html_script(cat_slug))
        payload = json.loads(result)

        if _is_blocked_response(payload):
            status = payload.get('status')
            title = payload.get('title') or ''
            raise RuntimeError(f'Nyon blocked (status={status}, title={title[:80]})')

        items = []
        for p in payload.get('products', []):
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
        
        display_currency = _detect_display_currency(price_str)
        display_price = _parse_money(price_str)
        item_price = _canonicalize_nyon_price(display_price, display_currency)
        item_currency = 'CHF'

        orig_price_str = raw.get('originalPrice', '')
        original_display_currency = _detect_display_currency(orig_price_str) if orig_price_str else display_currency
        original_display_price = _parse_money(orig_price_str) if orig_price_str else None
        item_original_price = _canonicalize_nyon_price(original_display_price, original_display_currency)
        
        full_name = f'{brand} {name}'
        
        return ScrapedItem(
            name=full_name,
            price=item_price,
            original_price=item_original_price,
            currency=item_currency,
            url=url,
            box_size=box_size,
            in_stock=in_stock,
            raw_data={
                'brand': brand,
                'product': name,
                'title_original': title,
                'price_original': price_str,
                'display_currency': display_currency,
                'display_price': display_price,
                'canonical_currency': 'CHF',
            }
        )
