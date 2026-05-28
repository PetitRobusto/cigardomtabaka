#!/usr/bin/env python3
"""
COH 中国站 一条龙数据管线
===========================
爬取 → 解析 → 清洗 → 匹配 → 入库

用法:
    python coh_pipeline.py           # 全量跑
    python coh_pipeline.py --dry-run # 只爬不存，看匹配率
    python coh_pipeline.py --brand Cohiba  # 只爬单品牌

依赖: Django + Playwright + BeautifulSoup
"""
import os
import sys
import asyncio
import argparse
import logging
from datetime import date

# ── Django 初始化 ──────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'moscow_cigar_backend.settings')
import django
django.setup()

from price_tracker.models import PriceSource, PriceSnapshot, ExchangeRate
from price_tracker.matcher import match_cigar, extract_brand_hint
from cigars.models import Cigar

logger = logging.getLogger('coh_pipeline')
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')


# ═══════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════

BASE_URL = 'https://www.cohcigars.com'

CREDENTIALS = {
    'username': 'maxx789789',
    'password': ';nykus8hvH@^h8X',
}

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


# ═══════════════════════════════════════════════════════════════════
# 第一关：爬取 + 解析
# ═══════════════════════════════════════════════════════════════════

async def scrape_all(brands: list[str] | None = None) -> list[dict]:
    """Playwright 登录 COH 中国站，爬取所有品牌产品"""
    from playwright.async_api import async_playwright
    import re
    from bs4 import BeautifulSoup
    import unicodedata

    target_brands = brands or list(BRAND_SLUGS.keys())

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        page = await context.new_page()

        # 登录
        logged_in = await _login(page)
        logger.info(f'登录: {"✓" if logged_in else "✗ (继续未登录爬取)"}')

        all_items = []

        for brand_name in target_brands:
            slug = BRAND_SLUGS.get(brand_name)
            if not slug:
                continue

            try:
                items = await _scrape_brand(page, brand_name, slug)
                all_items.extend(items)
                logger.info(f'{brand_name}: {len(items)} 款')
            except Exception as e:
                logger.warning(f'{brand_name}: {e}')

        await browser.close()

    # 去重
    seen = set()
    unique = []
    for item in all_items:
        key = (item['scraped_name'], item.get('box_size'))
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


async def _login(page) -> bool:
    """COH 登录"""
    await page.goto(f'{BASE_URL}/home.aspx', wait_until='domcontentloaded', timeout=30000)
    await page.wait_for_timeout(2000)

    body = await page.locator('body').inner_text()
    if 'MY INFO' in body or 'LOGOUT' in body:
        return True

    login_link = page.locator('a:has-text("Log In")')
    if await login_link.count() == 0:
        return False

    await login_link.first.click()
    await page.wait_for_timeout(3000)

    body = await page.locator('body').inner_text()
    if 'MY INFO' in body or 'LOGOUT' in body:
        return True

    if await page.locator('#txtUserID').count() == 0:
        return False

    await page.locator('#txtUserID').fill(CREDENTIALS['username'])
    await page.locator('#txtPassword').fill(CREDENTIALS['password'])

    try:
        chk = page.locator('#chkRemember')
        if await chk.count() > 0 and not await chk.is_checked():
            await chk.check()
    except Exception:
        pass

    await page.locator('#btnSubmit').click()
    await page.wait_for_timeout(4000)

    body = await page.locator('body').inner_text()
    return 'MY INFO' in body or 'LOGOUT' in body


async def _scrape_brand(page, brand_name: str, slug: str) -> list[dict]:
    """爬取单个品牌页 → 原始数据 dict 列表"""
    import re
    from bs4 import BeautifulSoup
    import unicodedata

    url = f'{BASE_URL}/cigars-{slug}?lang=zh-CN'

    for attempt in range(3):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)
            html = await page.content()
            items = _parse_html(html, brand_name)
            if items:
                return items
            await page.wait_for_timeout(2000)
        except Exception as e:
            if attempt < 2:
                logger.warning(f'{brand_name} 第{attempt+1}次失败: {e}')
                await page.wait_for_timeout(3000)
            else:
                raise
    return []


# ═══════════════════════════════════════════════════════════════════
# 第二关：HTML 解析（结构化提取）
# ═══════════════════════════════════════════════════════════════════

def _parse_html(html: str, brand_name: str) -> list[dict]:
    """结构化解析 COH 品牌页"""
    import re
    from bs4 import BeautifulSoup
    import unicodedata

    soup = BeautifulSoup(html, 'html.parser')
    product_spans = soup.find_all('span', class_=re.compile(r'product_header'))
    if not product_spans:
        return []

    items = []
    for span in product_spans:
        full_text = span.get_text(strip=True).replace('\xa0', ' ').strip()
        if ' - ' not in full_text:
            continue

        parts = full_text.split(' - ', 1)
        brand_from_page = parts[0].strip()
        product_name = parts[1].strip()

        if not _brand_match(brand_from_page):
            continue

        # 上行到 tbody → 找第二行详情
        tr = span.find_parent('tr')
        if not tr:
            continue
        tbody = tr.find_parent('tbody') or tr.find_parent('table')
        if not tbody:
            continue

        all_rows = tbody.find_all('tr', recursive=False)
        detail_tr = all_rows[1] if len(all_rows) >= 2 else None
        if not detail_tr:
            continue

        detail_text = detail_tr.get_text('\n')

        # 提取详情
        length_val = ''
        ring_val = ''
        box_info = ''
        price_str = ''
        box_size = None
        price = None

        for line in detail_text.split('\n'):
            line = line.strip()
            if re.match(r'Length.*inch', line, re.I):
                length_val = line
            elif re.match(r'Ring Gauge', line, re.I):
                ring_val = line
            elif re.search(r'(\d+)\s*(Box|Pack|Bundle|Single)', line, re.I):
                box_info = line
                prices = re.findall(r'\$\s*([\d,]+\.?\d*)', line)
                if prices:
                    price_str = prices[-1]

        if not price_str:
            for line in detail_text.split('\n'):
                if re.search(r'\$\s*[\d,]+', line):
                    prices = re.findall(r'\$\s*([\d,]+\.?\d*)', line)
                    if prices:
                        price_str = prices[-1]
                        break

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

        if price is not None:
            items.append({
                'scraped_name': f'{brand_from_page} {product_name}',
                'brand': brand_from_page,
                'product': product_name,
                'price_usd': price,
                'box_size': box_size,
                'length': length_val,
                'ring_gauge': ring_val,
                'box_info': box_info,
                'in_stock': True,
                'currency': 'USD',
            })

    return items


def _brand_match(brand: str) -> bool:
    """品牌名匹配"""
    import unicodedata

    def _norm(s):
        nfkd = unicodedata.normalize('NFKD', s)
        ascii_only = nfkd.encode('ascii', 'ignore').decode('ascii')
        return ascii_only.lower().replace('.', '').replace("'", '').replace(' ', '').replace('-', '')

    known = {_norm(b) for b in BRAND_SLUGS.keys()}
    nb = _norm(brand)
    if nb in known:
        return True

    ALIASES = {
        'quinteroyhermano': 'quintero',
        'sancristobaldelahabana': 'sancristobal',
    }
    return ALIASES.get(nb) in known


# ═══════════════════════════════════════════════════════════════════
# 第三关：清洗 + 匹配
# ═══════════════════════════════════════════════════════════════════

def clean_and_match(raw_items: list[dict]) -> list[dict]:
    """
    清洗数据 + 匹配 Cigar 模型

    返回: 每个 item 增加 matched_cigar / matched_name / match_confidence
    """
    results = []
    for item in raw_items:
        result = dict(item)  # copy

        # 匹配
        cigar = match_cigar(
            item['scraped_name'],
            brand_hint=extract_brand_hint(item['scraped_name']),
            prefer_current=True,
        )

        if cigar:
            result['matched_cigar'] = cigar
            result['matched_name'] = str(cigar)
            result['match_ok'] = True
        else:
            result['matched_cigar'] = None
            result['matched_name'] = None
            result['match_ok'] = False

        results.append(result)

    return results


# ═══════════════════════════════════════════════════════════════════
# 第四关：入库
# ═══════════════════════════════════════════════════════════════════

def save_to_db(items: list[dict], source_slug: str = 'coh_china', dry_run: bool = False):
    """
    将清洗后的数据写入 PriceSnapshot

    去重逻辑: 同 source + cigar + box_size + 同一天 → 更新价格
    """
    from django.utils import timezone

    source = PriceSource.objects.get(slug=source_slug)
    today = timezone.now().date()

    # 汇率
    rate_obj = ExchangeRate.get_rate('USD')
    usd_to_cny = rate_obj if rate_obj else 7.2

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'oos': 0}

    if dry_run:
        matched = sum(1 for i in items if i.get('match_ok'))
        logger.info(f'[DRY RUN] {len(items)} 款, 匹配 {matched}/{len(items)}')
        return stats

    # 处理匹配成功的
    seen_combos = set()
    for item in items:
        if not item.get('match_ok'):
            stats['skipped'] += 1
            continue

        cigar = item['matched_cigar']
        box_size = item.get('box_size')
        price_usd = item.get('price_usd')
        price_cny = round(price_usd * usd_to_cny, 2)

        seen_combos.add((cigar.id, box_size))

        existing = PriceSnapshot.objects.filter(
            source=source,
            cigar=cigar,
            box_size=box_size,
            scraped_date=today,
        ).first()

        if existing:
            existing.price = price_usd
            existing.price_cny = price_cny
            existing.in_stock = True
            existing.save()
            stats['updated'] += 1
        else:
            PriceSnapshot.objects.create(
                source=source,
                cigar=cigar,
                price=price_usd,
                price_cny=price_cny,
                currency='USD',
                box_size=box_size,
                url=f'{BASE_URL}/cigars-{BRAND_SLUGS.get(item.get("brand", ""), "")}',
                in_stock=True,
            )
            stats['created'] += 1

    # 缺货检测：昨天有货但今天没出现的 → 标记缺货
    prev_instock = PriceSnapshot.objects.filter(
        source=source, in_stock=True
    ).exclude(scraped_date=today).values_list('cigar_id', 'box_size').distinct()

    for cid, bs in prev_instock:
        if (cid, bs) not in seen_combos:
            existing_oods = PriceSnapshot.objects.filter(
                source=source, cigar_id=cid,
                box_size=bs, scraped_date=today
            ).exists()
            if not existing_oods:
                PriceSnapshot.objects.create(
                    source=source,
                    cigar_id=cid,
                    price=0,
                    price_cny=0,
                    currency='USD',
                    box_size=bs,
                    in_stock=False,
                    raw_data={'oos_detected': True},
                )
                stats['oos'] += 1

    source.last_scraped = timezone.now()
    source.save(update_fields=['last_scraped'])

    return stats


# ═══════════════════════════════════════════════════════════════════
# 第五关：报告
# ═══════════════════════════════════════════════════════════════════

def print_report(items: list[dict], stats: dict):
    """打印爬取报告"""
    total = len(items)
    matched = sum(1 for i in items if i.get('match_ok'))
    unmatched = total - matched

    print(f"""
╔══════════════════════════════════╗
║     COH 中国站 数据管线           ║
╠══════════════════════════════════╣
║  爬取:  {total:>4} 款                  ║
║  匹配:  {matched:>4} 款 ({matched*100//total if total else 0}%)           ║
║  未匹配: {unmatched:>4} 款                ║
╠══════════════════════════════════╣
║  新建:  {stats.get('created', 0):>4} 条                ║
║  更新:  {stats.get('updated', 0):>4} 条                ║
║  缺货:  {stats.get('oos', 0):>4} 条                ║
╚══════════════════════════════════╝
""")

    if unmatched:
        print('未匹配产品（爬虫原名 → 数据库）:')
        for item in items:
            if not item.get('match_ok'):
                print(f'  ✗ {item["scraped_name"]} → 无')

    # 匹配详情（前10条）
    print('\n匹配详情（前10条）:')
    matched_items = [i for i in items if i.get('match_ok')]
    for item in matched_items[:10]:
        print(f'  ✓ {item["scraped_name"]} → {item["matched_name"]}')

    # 按品牌统计
    from collections import Counter
    brand_counts = Counter(i['brand'] for i in items if i.get('match_ok'))
    print('\n按品牌:')
    for brand, count in brand_counts.most_common():
        print(f'  {brand}: {count}')


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description='COH 中国站一条龙数据管线')
    parser.add_argument('--dry-run', action='store_true', help='只爬不存')
    parser.add_argument('--brand', type=str, help='只爬单品牌')
    args = parser.parse_args()

    brands = [args.brand] if args.brand else None

    # 第一关：爬（async）
    print('🕷️  第一关：爬取 + 解析...')
    raw_items = await scrape_all(brands)

    # 第二关+第三关+第四关：清洗+匹配+入库（sync，扔线程避免 Django async 限制）
    import concurrent.futures
    loop = asyncio.get_event_loop()

    print(f'🧹 第二关：清洗 {len(raw_items)} 款 + 匹配...')
    cleaned = await loop.run_in_executor(None, clean_and_match, raw_items)

    # 入库
    if not args.dry_run:
        print('💾 第三关：入库...')
        stats = await loop.run_in_executor(None, save_to_db, cleaned, 'coh_china', False)
    else:
        stats = {}

    # 第五关：报告
    print_report(cleaned, stats)


if __name__ == '__main__':
    asyncio.run(main())
