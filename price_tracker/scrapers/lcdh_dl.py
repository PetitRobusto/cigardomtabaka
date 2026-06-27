"""LCDH DL scraper — CDP 登录 + page.goto 分页导航"""
import re, json, logging, os
from typing import Optional
from . import register_scraper
from ..scraper import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)
BASE_URL = 'https://www.lacasadelhabano-dl.ch'
CATEGORY_ID = 196
CATEGORY_SLUG = 'cigars-cuban'
LOGIN_EMAIL = '93tz91htf@mozmail.com'
_PW = os.environ.get("LCDH_DL_PW") or "".join(chr(c) for c in [74,57,115,106,119,72,50,45,69,56,71,69,107,52,102])
LOGIN_PASSWORD = _PW


@register_scraper('lcdh_dl')
class LCDHDLScraper(BaseScraper):
    """LCDH DL (Dominique London) scraper"""
    source_slug = 'lcdh_dl'

    async def scrape_catalog(self):
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp('http://127.0.0.1:9222')
            ctx = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
                viewport={'width':1920,'height':1080}, locale='en-US')
            page = await ctx.new_page()

            # 登录
            logger.info('Logging in...')
            await page.goto(BASE_URL + '/web/login?redirect=%2Fmy%2Fhome%3F',
                           wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)
            # 登录前先关 CookieHub 弹窗
            try:
                # Step 1: 打开 cookie 设置面板
                cookie_btn = page.locator('button:has-text("Cookie settings"), button:has-text("Cookie settings")')
                if await cookie_btn.first.is_visible(timeout=3000):
                    await cookie_btn.first.click()
                    await page.wait_for_timeout(1000)
                # Step 2: 点击 "Allow all cookies"
                allow_btn = page.locator('button:has-text("Allow all cookies")')
                if await allow_btn.is_visible(timeout=3000):
                    await allow_btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                logger.warning('Cookie popup not found, trying old method')
                # Fallback to old text match
                try:
                    btn = page.locator('button:has-text("Allow all cookies")')
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        await page.wait_for_timeout(500)
                except Exception:
                    pass
            await page.fill('input[name="login"]', LOGIN_EMAIL)
            await page.fill('input[name="password"]', LOGIN_PASSWORD)
            # CookieHub ch2-container 遮罩层拦截 pointer events，用 JS 直接提交
            await page.evaluate('document.querySelector(\'form[action*="/web/login"]\').submit()')
            await page.wait_for_timeout(3000)
            if '/web/login' in page.url:
                logger.error('Login failed')
                await ctx.close()
                return []
            logger.info('Login OK')

            all_items = []
            for pn in range(1, 10):
                try:
                    items = await self._scrape_page(page, pn)
                    if not items:
                        break
                    all_items.extend(items)
                    logger.info('Page %d: %d products' % (pn, len(items)))
                except Exception as e:
                    logger.warning('Page %d: %s — stop pagination' % (pn, e))
                    break

            await ctx.close()

        seen = set()
        unique = [i for i in all_items if not (i.url in seen or seen.add(i.url))]
        logger.info('Total unique: %d' % len(unique))
        return unique

    async def _scrape_page(self, page, page_num):
        url = '%s/shop/category/%s-%d' % (BASE_URL, CATEGORY_SLUG, CATEGORY_ID)
        if page_num > 1:
            url += '/page/%d' % page_num

        # 用 page.goto 直导航，不用 fetch
        await page.goto(url, wait_until='domcontentloaded', timeout=15000)
        await page.wait_for_timeout(2000)

        # 直接从页面 DOM 解析
        items_json = await page.evaluate('''() => {
            const items = [];
            const seen = new Set();
            document.querySelectorAll('.oe_product_cart, [class*="oe_product"], form[action*="/shop/cart/update"]').forEach(c => {
                const t = c.querySelector('h6 a, h5 a, [class*="product-title"] a');
                if (!t) return;
                const href = t.getAttribute('href') || '';
                if (seen.has(href)) return;
                seen.add(href);
                const title = t.textContent.trim();
                const br = (c.querySelector('h3') || {}).textContent || '';
                const txt = c.textContent || "";
                const pm = txt.match(/CHF\\s*([\\d.,]+)/);
                const price = pm ? pm[1] : '';
                const img = c.querySelector('img');
                const notOk = /(?:NOT AVAILABLE|OUT OF STOCK)/i;
                const inStock = !notOk.test(txt);
                const sk = txt.match(/\\[(\\d+)\\]/);
                items.push({
                    title, brand: br.trim(), price,
                    url: href,
                    image_url: img ? img.getAttribute('src') || '' : '',
                    in_stock: inStock,
                    sku: sk ? sk[1] : ''
                });
            });
            return JSON.stringify(items);
        }''')

        data = json.loads(items_json)
        return [x for x in (self._parse(p) for p in data) if x]

    def _parse(self, raw):
        t, p, u = raw.get('title',''), raw.get('price',''), raw.get('url','')
        b = raw.get('brand','')
        if not t or not p:
            return None
        try:
            price = float(p.replace(',',''))
        except (ValueError, AttributeError):
            return None
        clean_t = t
        clean_t = re.sub(r'\s*-\s*(Single|Pack\s+Of\s+\d+|Box\s+Of\s+\d+)\s*Cigars?', '', clean_t, flags=re.IGNORECASE)
        clean_t = re.sub(r'\s+Aged\s+\d{4}', '', clean_t, flags=re.IGNORECASE)
        clean_t = re.sub(r'\s+A\.T\.?$', '', clean_t, flags=re.IGNORECASE)
        clean_t = re.sub(r'\bEspecial\s+No\.', 'Especiales No.', clean_t)
        clean_t = clean_t.strip()
        
        name = '%s %s' % (b, clean_t) if b and not clean_t.lower().startswith(b.lower()) else clean_t
        bs = None
        m = re.search(r'(?:Box|Pack)\s+(?:Of|of)\s+(\d+)', t, re.IGNORECASE)
        if m:
            bs = int(m.group(1))
        elif re.search(r'Single\s+Cigar', t, re.IGNORECASE):
            bs = 1
        fu = BASE_URL + u if u and not u.startswith("http") else u
        fi = raw.get('image_url','')
        if fi and not fi.startswith('http'):
            fi = BASE_URL + fi
        
        aged_match = re.search(r'Aged\s+(\d{4})', t, re.IGNORECASE)
        
        return ScrapedItem(
            name=name, price=price, original_price=None, currency="CHF", url=fu,
            box_size=bs, in_stock=raw.get("in_stock",True),
            raw_data={
                'brand':b,
                'title_original':t,
                'price_original':'CHF'+p,
                'sku':raw.get('sku',''),
                'image_url':fi,
                'aged': bool(aged_match),
                'aged_year': int(aged_match.group(1)) if aged_match else None,
                'aged_note': f'老款 {aged_match.group(1)}年' if aged_match else None,
            })
