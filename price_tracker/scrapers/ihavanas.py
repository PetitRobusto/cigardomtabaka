"""iHavanas 价格爬虫 - 待完善"""
from price_tracker.scraper import BaseScraper, ScrapedItem
from price_tracker.scrapers import register_scraper


@register_scraper('ihavanas')
class IhavanasScraper(BaseScraper):
    """
    iHavanas (ihavanas.com) 爬虫

    TODO: 实际爬取逻辑
    网站有 Cloudflare 防护，需用 Playwright/CDP 绕过。
    产品列表页结构待分析。

    适配步骤：
    1. 用 browser_navigate 或 CDP 打开 https://ihavanas.com/cigars
    2. 解析产品卡片提取：品名、价格、盒装规格、库存
    3. 翻页遍历全站
    4. 返回 ScrapedItem 列表
    """

    async def scrape_catalog(self) -> list[ScrapedItem]:
        # 占位：返回空列表，等实测网站后再完善
        return []
