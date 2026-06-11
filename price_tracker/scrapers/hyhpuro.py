"""
HYHPURO 爬虫 (hyhpuro.com)
西班牙古巴雪茄站，香港发货，Ueeshop 平台

URL 模式：
- 主列表：https://hyhpuro.com/collections/所有商品?page=N
- 产品行：div.themes_prod.list_products_item
- 产品详情：/products/{slug}

产品信息（列表页）：
- 品名：a.item_name.themes_products_title 文本（中英双语）
- URL：a.item_name href
- 售价：span.price_data[data="1398"] — data 属性是纯数字
- 原价：del > span.price_data[data]
- 产品 ID：span.price_data[keyid]
- 折扣：div.themes_sales 文本
- 币种：EUR
- 库存：文本中 "(N)" 括号数字
- 图片：img[data-srcset]（懒加载）

分页策略：
- ?page=N 参数，超出范围会循环回绕到 page 1
- 用 URL 去重检测回绕
- 到空页或连续重复页停止
"""
import re
import logging
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from . import register_scraper
from ..scraper import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)

BASE_URL = 'https://hyhpuro.com'
COLLECTION_URL = f'{BASE_URL}/collections/所有商品'

MAX_PAGES = 30  # 安全上限（实际 ~22 页）


def _extract_box_size(text: str) -> Optional[int]:
    """从品名提取盒装支数：'20s', '25支/盒', '10支'"""
    # Pattern 1: "20s" (space + digits + s)
    m = re.search(r'\b(\d+)s\b', text)
    if m:
        return int(m.group(1))
    # Pattern 2: "25支/盒", "10支"
    m = re.search(r'(\d+)\s*支', text)
    if m:
        return int(m.group(1))
    # Pattern 3: "Box of 20"
    m = re.search(r'(?:Box|Cabinet|Pack)\s+(?:of\s+)?(\d+)', text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _extract_stock(text: str) -> Optional[int]:
    """从 '(29)' 格式括号提取库存数"""
    m = re.search(r'\((\d+)\)', text)
    if m:
        return int(m.group(1))
    return None


def _clean_name(title: str) -> str:
    """从双语标题中提取英文名（中文之前的部分），合并多余空格"""
    cn_match = re.search(r'[\u4e00-\u9fff]', title)
    if cn_match:
        name = title[:cn_match.start()]
    else:
        name = title
    # 合并不规则空格（非ASCII空格 + 多个空格 → 单个空格）
    name = re.sub(r'[\s\u3000]+', ' ', name).strip()
    # 清理特殊字符
    name = name.replace('–', '-').replace('—', '-')
    return name


@register_scraper('hyhpuro')
class HYHPUROScraper(BaseScraper):
    """HYHPURO 爬虫 — httpx + BeautifulSoup"""

    source_slug = 'hyhpuro'

    async def scrape_catalog(self) -> list[ScrapedItem]:
        import asyncio

        all_items = []
        seen_urls = set()
        consecutive_empty = 0

        async with httpx.AsyncClient(
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            },
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            for page in range(1, MAX_PAGES + 1):
                url = f'{COLLECTION_URL}?page={page}'
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    items, new_urls = self._parse_list_html(resp.text)

                    if not items:
                        consecutive_empty += 1
                        if consecutive_empty >= 2:
                            break
                        continue
                    consecutive_empty = 0

                    # 回绕检测：新 URL 全部已见过 → 停止
                    if new_urls and seen_urls.issuperset(new_urls):
                        logger.info(f'Page {page}: all URLs already seen, stopping (wrap detected)')
                        break

                    seen_urls.update(new_urls)
                    all_items.extend(items)
                    logger.info(f'Page {page}: {len(items)} products (cumulative: {len(seen_urls)} URLs)')

                except Exception as e:
                    logger.error(f'Page {page}: {e}')
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break

        # 去重：同 URL + 同 box_size 只保留有价格的那条
        seen = {}
        for item in all_items:
            key = (item.url, item.box_size)
            if key not in seen:
                seen[key] = item
            elif item.price is not None and seen[key].price is None:
                seen[key] = item

        unique = list(seen.values())
        logger.info(f'HYHPURO total: {len(unique)} unique products (from {len(all_items)} raw)')
        return unique

    def _parse_list_html(self, html: str) -> tuple[list[ScrapedItem], set[str]]:
        """解析列表页 HTML，返回 (items, new_urls)"""
        soup = BeautifulSoup(html, 'html.parser')
        items = []
        new_urls = set()

        for prod in soup.find_all('div', class_=lambda c: c and 'themes_prod' in c and 'list_products_item' in c):
            item, url = self._parse_product(prod)
            if item:
                items.append(item)
                if url:
                    new_urls.add(url)

        return items, new_urls

    def _parse_product(self, prod) -> tuple[Optional[ScrapedItem], str]:
        """解析单个产品 div，返回 (item, url)"""
        # 品名 + URL
        name_el = prod.find('a', class_='item_name')
        if not name_el:
            return None, ''
        title = name_el.get_text(strip=True)
        url = name_el.get('href', '')
        if url and not url.startswith('http'):
            url = urljoin(BASE_URL, url)

        # 售价：span.price_data
        # 在售商品: data="1398"（纯整数）; 售罄商品: data-mall-price="1160.00"（浮点）
        price_span = prod.find('span', class_='price_data')
        sale_price = None
        is_sold_out = False
        if price_span:
            data_val = price_span.get('data', '')
            try:
                sale_price = float(data_val) if data_val else None
            except (ValueError, TypeError):
                sale_price = None
            # 售罄商品：data 为空，价格在 data-mall-price 中
            if sale_price is None:
                mall_price = price_span.get('data-mall-price', '').strip()
                if mall_price:
                    try:
                        sale_price = float(mall_price)
                    except (ValueError, TypeError):
                        pass
            # 检测售罄状态
            classes = price_span.get('class', [])
            if isinstance(classes, str):
                classes = classes.split()
            is_sold_out = 'sold_out_price' in classes or price_span.get_text(strip=True) == '已售罄'

        # 原价：del 下的 span.price_data
        del_el = prod.find('del', class_='themes_products_origin_price')
        original_price = None
        if del_el:
            orig_span = del_el.find('span', class_='price_data')
            if orig_span:
                data_val = orig_span.get('data', '')
                try:
                    original_price = float(data_val) if data_val else None
                except (ValueError, TypeError):
                    original_price = None

        # 跳过无价格产品
        if sale_price is None and original_price is None:
            logger.debug(f'Skip no-price: {title[:50]}')
            return None, url

        # 产品 ID
        product_id = price_span.get('keyid', '') if price_span else ''

        # 盒装数
        box_size = _extract_box_size(title)

        # 库存
        prod_text = prod.get_text()
        stock_qty = _extract_stock(prod_text)
        in_stock = not is_sold_out and (stock_qty is None or stock_qty > 0)

        # 折扣标签
        discount_el = prod.find('div', class_='themes_sales')
        discount = discount_el.get_text(strip=True) if discount_el else None

        # 提取英文名
        name_clean = _clean_name(title)

        # 品牌提取（从品名第一个词）
        brand = None
        if name_clean:
            brand = name_clean.split()[0]

        return ScrapedItem(
            name=name_clean,
            price=sale_price,
            original_price=original_price,
            box_size=box_size,
            url=url,
            in_stock=in_stock,
            currency='EUR',
            raw_data={
                'title': title,
                'brand': brand,
                'product_id': product_id,
                'discount': discount,
                'stock': stock_qty,
            },
        ), url
