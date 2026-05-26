"""爬虫注册 — 按 source_slug 映射到对应爬虫类"""
from price_tracker.scraper import BaseScraper

# 注册表：slug → scraper class
_registry: dict[str, type[BaseScraper]] = {}


def register_scraper(slug: str):
    """装饰器：注册爬虫类"""
    def wrapper(cls):
        cls.source_slug = slug
        _registry[slug] = cls
        return cls
    return wrapper


def get_scraper(slug: str) -> type[BaseScraper] | None:
    """按 slug 获取爬虫类"""
    # 懒加载：首次访问时导入所有爬虫模块
    if not _registry:
        _load_scrapers()
    return _registry.get(slug)


def list_scrapers() -> list[str]:
    if not _registry:
        _load_scrapers()
    return list(_registry.keys())


def _load_scrapers():
    """懒加载：导入所有爬虫模块"""
    import importlib
    import pkgutil
    import price_tracker.scrapers as pkg
    for _, modname, _ in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f'price_tracker.scrapers.{modname}')
