"""
LCDH Nyon 爬虫 (la-casa-del-habano-nyon.com)
瑞士雪茄店，WooCommerce + Flatsome主题
Cloudflare防护 → 复用 9222 CDP 浏览器会话绕过
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



def _brand_parse_script() -> str:
    return '''
            () => {
                const products = [];
                document.querySelectorAll('.product-small, li.product').forEach(card => {
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
                    products.push({
                        title: titleEl.textContent.trim(),
                        price: priceText,
                        originalPrice: origPriceText,
                        url: linkEl?.getAttribute('href') || '',
                        badge: oosLabel?.textContent?.trim() || (isOOS ? 'Out of stock' : ''),
                        inStock: !isOOS
                    });
                });
                return JSON.stringify(products);
            }
        '''

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
    """LCDH Nyon 爬虫 — 复用 9222 CDP 浏览器绕过 Cloudflare"""
    
    source_slug = 'lcdh_nyon'
    
    async def scrape_catalog(self) -> list[ScrapedItem]:
        from playwright.async_api import async_playwright

        all_items = []
        brand_list = list(BRAND_CATEGORIES.items())
        page = None
        created_context = False

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp('http://127.0.0.1:9222')
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                               '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US'
                )
                created_context = True

            try:
                page = await context.new_page()
                await page.goto(f'{BASE_URL}/en/?currency=CHF',
                               wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(3000)

                body = await page.locator('body').inner_text()
                if '安全验证' in body or 'challenge' in body.lower() or 'security verification' in body.lower():
                    logger.warning('Nyon CF 封锁')
                    return []

                await page.evaluate('''() => {
                    document.cookie = "woocs=CHF;path=/;max-age=86400";
                    document.cookie = "currency=CHF;path=/;max-age=86400";
                }''')

                consecutive_failures = 0
                for cat_slug, brand_name in brand_list:
                    try:
                        items = await self._scrape_brand(page, brand_name, cat_slug)
                        all_items.extend(items)
                        consecutive_failures = 0
                        logger.info(f'  {brand_name}: {len(items)} products')
                    except Exception as e:
                        err_msg = str(e)
                        if 'rate limited' in err_msg.lower() or '429' in err_msg:
                            raise RuntimeError(err_msg) from e
                        consecutive_failures += 1

                        if 'Execution context was destroyed' in err_msg or consecutive_failures >= 3:
                            logger.warning(f'  {brand_name}: page dead, rebuilding ({err_msg[:60]})')
                            try:
                                await page.close()
                            except Exception:
                                pass
                            page = await context.new_page()
                            await page.goto(f'{BASE_URL}/en/?currency=CHF',
                                           wait_until='domcontentloaded', timeout=30000)
                            await page.wait_for_timeout(2000)
                            consecutive_failures = 0
                            try:
                                items = await self._scrape_brand(page, brand_name, cat_slug)
                                all_items.extend(items)
                                logger.info(f'  {brand_name}: {len(items)} products (retry)')
                            except Exception as e2:
                                logger.warning(f'  {brand_name} retry failed: {str(e2)[:80]}')
                        else:
                            logger.warning(f'  {brand_name}: {err_msg[:80]}')

            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                if created_context:
                    try:
                        await context.close()
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
        """Navigate to one brand page and parse the rendered DOM."""
        url = f'{BASE_URL}/en/product-category/cigares-cubains/{cat_slug}/?currency=CHF'
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(600)
        try:
            await page.wait_for_selector('.product-small, li.product', timeout=1000)
        except Exception:
            pass

        title = await page.title()
        body_head = (await page.locator('body').inner_text())[:800]
        if '429' in title or 'too many requests' in body_head.lower():
            raise RuntimeError('Nyon rate limited (429 Too Many Requests)')
        if 'Just a moment' in title or 'security verification' in body_head.lower():
            raise RuntimeError('Cloudflare security verification page')

        result = await page.evaluate(_brand_parse_script())

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
