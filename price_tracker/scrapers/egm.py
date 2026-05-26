"""EGM Cigars 价格爬虫 - 待完善"""
from price_tracker.scraper import BaseScraper, ScrapedItem
from price_tracker.scrapers import register_scraper


@register_scraper('egm')
class EGMCigarsScraper(BaseScraper):
    """
    EGM Cigars (egmcigars.com) 爬虫

    TODO: 实际爬取逻辑
    网站通常有 REST API 或 GraphQL 后端，可能不需要浏览器级别反爬。
    先尝试 API 直连，失败再切 Playwright。

    适配步骤：
    1. 抓取产品列表 API
    2. 解析 JSON 提取：品名、价格、盒装规格、库存
    3. 返回 ScrapedItem 列表
    """

    async def scrape_catalog(self) -> list[ScrapedItem]:
        # 占位
        return []
