"""
COH Cigars 中国站爬虫 (cigarsofhabanos.com / cohcigars.com)

与 coh.py（国际站，无需登录）的区别：
1. 需要登录才能看到完整价格
2. 中国站（lang=zh-CN）可能有额外产品
3. 使用 Playwright 过 Cloudflare + 处理 ASP.NET WebForms 登录

登录机制：ASP.NET WebForms
- 表单字段：txtUserID, txtPassword
- 需要 __VIEWSTATE / __EVENTVALIDATION 等隐藏字段
- 登录成功后 session 由 ASP.NET_SessionId cookie 维护

URL 模式：
- 品牌页：/cigars-{slug}?lang=zh-CN
- 中国站语言参数 ?lang=zh-CN 触发中文界面
"""
import re
import json
import logging
import os
from typing import Optional

from . import register_scraper
from ..scraper import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)

BASE_URL = 'https://www.cohcigars.com'

# 品牌名 → COH slug 映射
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
    "Quai d'Orsay": 'quai-dorsay',
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

# 已知品牌名（用于页面解析时验证品牌行）
KNOWN_BRANDS = set(BRAND_SLUGS.keys())

# --- 凭据读取 ---

def _get_credentials() -> tuple[str, str]:
    """从环境变量或默认值读取 COH 登录凭据"""
    # 默认凭据（环境变量可覆盖）
    user = os.environ.get('COH_USERNAME', 'maxx789789')
    password = os.environ.get('COH_PASSWORD', ';nykus8hvH@^h8X')
    return user, password


# --- HTML 解析（从现有 coh.py 提取，增强版） ---

def _parse_coh_page(html: str, brand_name: str) -> list[ScrapedItem]:
    """解析 COH 品牌页 HTML，提取产品列表"""
    from bs4 import BeautifulSoup
    import unicodedata

    soup = BeautifulSoup(html, 'html.parser')

    # 优先用结构化解析：找 product_header / product_header_W 类 span
    items = _parse_structured(soup, brand_name)
    if items:
        return items

    # 兜底：纯文本解析（兼容性）
    text = soup.get_text('\n')
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return _parse_text_lines(lines, brand_name)


def _parse_structured(soup, brand_name: str) -> list[ScrapedItem]:
    """结构化解析：通过 product_header span → TBODY → 第二行提取价格

    COH 页面结构（每个产品）：
    <tbody>
      <tr><td><span class="product_header">Cohiba - Behike BHK 52</span></td></tr>
      <tr>
        <td><img></td>
        <td>Length/Ring/Price Grid...</td>
      </tr>
    </tbody>
    """
    items = []
    product_spans = soup.find_all('span', class_=re.compile(r'product_header'))
    if not product_spans:
        return []

    for span in product_spans:
        full_text = span.get_text(strip=True)
        full_text = full_text.replace('\xa0', ' ').strip()
        if ' - ' not in full_text:
            continue

        parts = full_text.split(' - ', 1)
        brand_from_page = parts[0].strip()
        product_name = parts[1].strip()

        if not _brand_matches(brand_from_page):
            continue

        full_name = f'{brand_from_page} {product_name}'

        # 上行链路：span → td → tr → tbody
        tr = span.find_parent('tr')
        if not tr:
            continue
        tbody = tr.find_parent('tbody')
        if not tbody:
            tbody = tr.find_parent('table')  # 兜底

        if not tbody:
            continue

        # 找到详情行（第二个 tr，或者包含价格信息的 tr）
        all_rows = tbody.find_all('tr', recursive=False)
        detail_tr = None
        if len(all_rows) >= 2:
            detail_tr = all_rows[1]  # 第二个 tr 是详情行
        elif tbody.name == 'table':
            # 可能价格在后续的 tr 里
            for r in all_rows:
                if _has_price_line(r.get_text()):
                    detail_tr = r
                    break

        if not detail_tr:
            continue

        detail_text = detail_tr.get_text('\n')
        length_val, ring_val, box_info, price_str, box_size, price, orig_price = \
            _extract_product_details(detail_text)

        if full_name and price is not None:
            items.append(ScrapedItem(
                name=full_name,
                price=price,
                original_price=orig_price if orig_price and orig_price != price else None,
                box_size=box_size,
                box_price=price,
                url=f'{BASE_URL}/cigars-{BRAND_SLUGS.get(brand_name, brand_name.lower().replace(" ", "-"))}',
                in_stock=True,
                currency='USD',
                raw_data={
                    'brand': brand_from_page,
                    'product': product_name,
                    'length': length_val,
                    'ring_gauge': ring_val,
                    'box_info': box_info,
                    'price_original': price_str,
                    'source': 'coh_china',
                },
            ))

    return items


def _has_price_line(text: str) -> bool:
    """检查文本是否包含价格信息"""
    return bool(re.search(r'\$\s*[\d,]+\.?\d*', text))


def _parse_text_lines(lines: list[str], brand_name: str) -> list[ScrapedItem]:
    """纯文本兜底解析"""
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
        if nav_patterns.match(line):
            i += 1
            continue

        name_match = re.match(r'^([A-Za-zÀ-ÿ][\wÀ-ÿ\.\s\'&]+?)\s*-\s*(.+)$', line)
        if name_match:
            brand_from_line = name_match.group(1).strip()
            product_name = name_match.group(2).strip()

            if not _brand_matches(brand_from_line):
                i += 1
                continue

            full_name = f'{brand_from_line} {product_name}'
            length_val = ''
            ring_val = ''
            box_info = ''
            price_str = ''
            orig_price_str = ''

            i += 1
            while i < len(lines):
                nl = lines[i]
                if re.match(r'^([A-Za-zÀ-ÿ][\wÀ-ÿ\.\s\'&]+?)\s*-\s*.+$', nl):
                    break
                if 'You must be 18' in nl or 'HOME' == nl or 'FAQ' in nl:
                    break
                if re.match(r'Length.*inch', nl, re.I):
                    length_val = nl
                elif re.match(r'Ring Gauge', nl, re.I):
                    ring_val = nl
                elif re.search(r'(\d+)\s*(Box|Pack|Bundle|Single)', nl, re.I):
                    box_info = nl
                    prices = re.findall(r'\$\s*([\d,]+\.?\d*)', nl)
                    if len(prices) >= 2:
                        price_str, orig_price_str = prices[-1], prices[0]
                    elif prices:
                        price_str = prices[-1]
                elif re.search(r'\$\s*[\d,]+', nl):
                    prices = re.findall(r'\$\s*([\d,]+\.?\d*)', nl)
                    if len(prices) >= 2:
                        price_str, orig_price_str = prices[-1], prices[0]
                    elif prices:
                        price_str = prices[-1]
                i += 1

            box_size, price = _parse_size_price(box_info, price_str)
            orig_price = None
            if orig_price_str:
                try:
                    orig_price = float(orig_price_str.replace(',', ''))
                except ValueError:
                    pass

            if full_name and price is not None:
                items.append(ScrapedItem(
                    name=full_name,
                    price=price,
                    original_price=orig_price if orig_price and orig_price != price else None,
                    box_size=box_size,
                    box_price=price,
                    url=f'{BASE_URL}/cigars-{BRAND_SLUGS.get(brand_name, brand_name.lower().replace(" ", "-"))}',
                    in_stock=True,
                    currency='USD',
                    raw_data={
                        'brand': brand_from_line,
                        'product': product_name,
                        'length': length_val,
                        'ring_gauge': ring_val,
                        'box_info': box_info,
                        'price_original': price_str,
                        'source': 'coh_china',
                    },
                ))
        i += 1

    return items


def _extract_product_details(text: str) -> tuple:
    """从产品区文本提取详细信息 (返回 8-tuple，含 orig_price)"""
    length_val = ''
    ring_val = ''
    box_info = ''
    price_str = ''
    orig_price_str = ''
    box_size = None
    price = None
    orig_price = None

    def _capture_prices(prices: list, pstr: str, opstr: str) -> tuple:
        if len(prices) >= 2:
            return prices[-1], prices[0]  # 最后一个=售价, 第一个=原价
        elif prices:
            return prices[-1], ''
        return pstr, opstr

    for line in text.split('\n'):
        line = line.strip()
        if re.match(r'Length.*inch', line, re.I):
            length_val = line
        elif re.match(r'Ring Gauge', line, re.I):
            ring_val = line
        elif re.search(r'(\d+)\s*(Box|Pack|Bundle|Single)', line, re.I):
            box_info = line
            prices = re.findall(r'\$\s*([\d,]+\.?\d*)', line)
            price_str, orig_price_str = _capture_prices(prices, price_str, orig_price_str)

    # 如果没从 box_info 行找到价格，尝试找带 $ 的行
    if not price_str:
        for line in text.split('\n'):
            if re.search(r'\$\s*[\d,]+', line):
                prices = re.findall(r'\$\s*([\d,]+\.?\d*)', line)
                price_str, orig_price_str = _capture_prices(prices, price_str, orig_price_str)
                if price_str:
                    break

    box_size, price = _parse_size_price(box_info, price_str)
    if orig_price_str:
        try:
            orig_price = float(orig_price_str.replace(',', ''))
        except ValueError:
            pass
    return length_val, ring_val, box_info, price_str, box_size, price, orig_price


def _parse_size_price(box_info: str, price_str: str) -> tuple:
    """解析盒装数量和价格"""
    box_size = None
    price = None

    if box_info:
        m = re.match(r'(\d+)(?:x(\d+))?\s*(?:Box|Pack|Bundle|Single)', box_info, re.I)
        if m:
            a = int(m.group(1))
            b = m.group(2)
            box_size = a * int(b) if b else a
        elif re.search(r'Single', box_info, re.I):
            box_size = 1

    if price_str:
        try:
            price = float(price_str.replace(',', ''))
        except ValueError:
            pass

    return box_size, price


def _brand_matches(brand: str) -> bool:
    """检查品牌名是否匹配已知古巴品牌"""
    import unicodedata

    def _normalize(s: str) -> str:
        nfkd = unicodedata.normalize('NFKD', s)
        ascii_only = nfkd.encode('ascii', 'ignore').decode('ascii')
        # 去掉标点、空格、连字符、撇号
        return (ascii_only.lower()
                .replace('.', '')
                .replace("'", '')
                .replace(' ', '')
                .replace('-', ''))

    known_normalized = {_normalize(b) for b in KNOWN_BRANDS}
    normalized_brand = _normalize(brand)

    if normalized_brand in known_normalized:
        return True

    # 别名映射：处理 COH 网站上的品牌名变体
    ALIASES = {
        'quaidorsay': 'quaidorsay',    # Quai Dorsay (no apostrophe)
        'quinteroyhermano': 'quintero',  # Quintero Y Hermano → Quintero
        'sancristobaldelahabana': 'sancristobal',  # San Cristobal De La Habana
    }
    if normalized_brand in ALIASES:
        return ALIASES[normalized_brand] in known_normalized

    return False


# --- Playwright 登录 + 爬取 ---

async def _login_coh(page) -> bool:
    """在 Playwright page 上登录 COH"""
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeout
    except ImportError:
        from asyncio import TimeoutError as PlaywrightTimeout

    # Step 1: 打开首页（warm up session）
    await page.goto(f'{BASE_URL}/home.aspx', wait_until='domcontentloaded', timeout=30000)
    await page.wait_for_timeout(2000)

    # 检查是否已登录
    body_text = await page.locator('body').inner_text()
    if 'MY INFO' in body_text or 'LOGOUT' in body_text:
        logger.info('COH: 已登录（cookie 有效）')
        return True

    # Step 2: 点击 Log In 链接（触发 ASP.NET postback 生成登录表单）
    login_link = page.locator('a:has-text("Log In")')
    login_count = await login_link.count()
    if login_count == 0:
        # 尝试中文版
        login_link = page.locator('a:has-text("登录")')
        login_count = await login_link.count()

    if login_count == 0:
        logger.error('COH: 找不到登录链接')
        return False

    await login_link.first.click()
    await page.wait_for_timeout(3000)

    # 再次检查是否已登录（click 可能触发了自动登录）
    body_text = await page.locator('body').inner_text()
    if 'MY INFO' in body_text or 'LOGOUT' in body_text:
        logger.info('COH: 点击登录链接后自动登录')
        return True

    # 获取凭据
    user, password = _get_credentials()
    if not user or not password:
        logger.error('COH 登录失败：未设置 COH_USERNAME / COH_PASSWORD 环境变量')
        return False

    # Step 3: 填充登录表单
    if await page.locator('#txtUserID').count() == 0:
        logger.error('COH 登录表单未出现')
        return False

    try:
        await page.locator('#txtUserID').fill(user)
        await page.locator('#txtPassword').fill(password)
    except PlaywrightTimeout as e:
        logger.error(f'COH 登录表单填充失败: {e}')
        return False

    # 勾选 Remember me
    try:
        chk = page.locator('#chkRemember')
        if await chk.count() > 0:
            is_checked = await chk.is_checked()
            if not is_checked:
                await chk.check()
    except Exception:
        pass

    # 点击登录
    await page.locator('#btnSubmit').click()
    await page.wait_for_timeout(4000)

    # 验证登录结果
    body_text = await page.locator('body').inner_text()
    if 'MY INFO' in body_text or 'LOGOUT' in body_text:
        logger.info('COH 登录成功')
        return True

    logger.error('COH 登录失败')
    return False


def _slug_for_brand(brand_name: str) -> str:
    """品牌名 → COH slug"""
    return BRAND_SLUGS.get(brand_name, brand_name.lower().replace(' ', '-'))


# --- 注册爬虫 ---

@register_scraper('coh_china')
class COHChinaScraper(BaseScraper):
    """
    COH Cigars 中国站爬虫

    特性：
    - Playwright 过 Cloudflare
    - 登录凭据从环境变量读取（COH_USERNAME / COH_PASSWORD）
    - 中国站 lang=zh-CN 参数
    - 独立模块，不影响现有 coh.py
    """

    source_slug = 'coh_china'

    def __init__(self, source, browser_page=None):
        super().__init__(source)
        self._page = browser_page  # 可选：复用已有浏览器页

    async def scrape_catalog(self) -> list[ScrapedItem]:
        """独立运行：启动 Playwright + stealth，登录，遍历品牌爬取"""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
            )
            page = await context.new_page()

            try:
                # Step 1: 登录
                logged_in = await _login_coh(page)
                if not logged_in:
                    logger.warning('COH 登录失败，尝试未登录爬取（可能缺省部分产品）')

                # Step 2: 遍历品牌
                all_items = []
                for brand_name, slug in BRAND_SLUGS.items():
                    try:
                        items = await self._scrape_brand(page, brand_name, slug)
                        all_items.extend(items)
                        logger.info(f'COH中国 {brand_name}: {len(items)} 款')
                    except Exception as e:
                        logger.warning(f'COH中国 {brand_name} 失败: {e}')

            finally:
                await browser.close()

        # 去重（按 name+box_size 组合）
        seen = set()
        unique = []
        for item in all_items:
            key = (item.name, item.box_size)
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique

    async def _scrape_brand(self, page, brand_name: str, slug: str) -> list[ScrapedItem]:
        """爬取单个品牌页（中国站），带重试"""
        url = f'{BASE_URL}/cigars-{slug}?lang=zh-CN'

        for attempt in range(3):
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
                html = await page.content()
                items = _parse_coh_page(html, brand_name)
                if items:
                    return items
                # 空结果可能 Cloudflare 拦截，等一下再试
                await page.wait_for_timeout(2000)
            except Exception as e:
                if attempt < 2:
                    logger.warning(f'COH中国 {brand_name} 第{attempt+1}次失败: {e}，重试...')
                    await page.wait_for_timeout(3000)
                else:
                    raise

        return []
