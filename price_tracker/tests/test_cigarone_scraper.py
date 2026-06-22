from price_tracker.scraper import ScrapedItem
from price_tracker.scrapers.cigarone import CigarOneScraper


def test_dedupe_drops_reference_price_when_boxed_row_exists():
    scraper = CigarOneScraper(source=None)
    url = 'https://www.cigarone.com/habanos-and-more-brands/partagas/cedros.html'

    items = [
        ScrapedItem(
            name='Partagas Cedros',
            price=76.67,
            box_size=None,
            url=url,
            currency='CHF',
        ),
        ScrapedItem(
            name='Partagas Cedros',
            price=1173.0,
            box_size=18,
            url=url,
            currency='CHF',
        ),
    ]

    deduped = scraper._dedupe_catalog_items(items)

    assert len(deduped) == 1
    assert deduped[0].box_size == 18
    assert deduped[0].price == 1173.0


def test_dedupe_keeps_single_unboxed_row_when_no_boxed_row_exists():
    scraper = CigarOneScraper(source=None)
    item = ScrapedItem(
        name='Trinidad Single',
        price=42.0,
        box_size=None,
        url='https://www.cigarone.com/habanos-and-more-brands/trinidad/single.html',
        currency='CHF',
    )

    assert scraper._dedupe_catalog_items([item]) == [item]
