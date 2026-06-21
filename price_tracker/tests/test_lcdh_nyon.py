"""LCDH Nyon scraper parsing tests."""
import pytest

from price_tracker.models import PriceSource
from price_tracker.scrapers.lcdh_nyon import (
    LCDHNyonScraper,
    _brand_parse_from_html_script,
    _brand_parse_script,
    _is_blocked_response,
    _nyon_delay_ms,
)


@pytest.fixture
def scraper(db):
    source = PriceSource.objects.create(
        name='LCDH Nyon',
        slug='lcdh_nyon',
        base_url='https://la-casa-del-habano-nyon.com',
        scraper_class='lcdh_nyon',
        currency='CHF',
    )
    return LCDHNyonScraper(source)


def test_parse_product_keeps_chf_price(scraper):
    item = scraper._parse_product(
        {
            'title': 'San Cristóbal De La Habana 20 Aniversario LCDH Vintage (20)',
            'price': 'Swiss franc\xa02,850.00',
            'url': 'https://la-casa-del-habano-nyon.com/en/boutique/example/',
            'inStock': False,
        },
        'San Cristóbal',
    )

    assert item is not None
    assert item.price == 2850.0
    assert item.currency == 'CHF'
    assert item.raw_data['display_currency'] == 'CHF'
    assert item.raw_data['display_price'] == 2850.0


def test_parse_product_normalizes_eur_display_to_chf(scraper):
    item = scraper._parse_product(
        {
            'title': 'San Cristóbal De La Habana 20 Aniversario LCDH Vintage (20)',
            'price': '€\xa03,163.50',
            'url': 'https://la-casa-del-habano-nyon.com/en/boutique/example/',
            'inStock': False,
        },
        'San Cristóbal',
    )

    assert item is not None
    assert item.price == 2850.0
    assert item.currency == 'CHF'
    assert item.raw_data['display_currency'] == 'EUR'
    assert item.raw_data['display_price'] == 3163.5



def test_brand_parse_script_reads_rendered_product_cards():
    script = _brand_parse_script()

    assert "document.querySelectorAll('.product-small, li.product')" in script
    assert 'JSON.stringify(products)' in script
    assert "a[href*=\"/boutique/\"]" in script


def test_brand_parse_from_html_script_fetches_detached_document():
    script = _brand_parse_from_html_script('cohiba')

    assert 'fetch("/en/product-category/cigares-cubains/cohiba/")' in script
    assert 'div.innerHTML = html' in script
    assert "div.querySelectorAll('.product-small, li.product')" in script
    assert 'JSON.stringify({' in script
    assert 'products' in script


def test_brand_parse_from_html_script_rejects_invalid_category_slug():
    with pytest.raises(ValueError, match='invalid Nyon category slug'):
        _brand_parse_from_html_script("cohiba'); throw new Error('boom")


@pytest.mark.parametrize(
    ('payload', 'expected'),
    [
        ({'status': 429, 'title': '', 'bodyHead': ''}, True),
        ({'status': 200, 'title': '429 Too Many Requests', 'bodyHead': ''}, True),
        ({'status': 200, 'title': '', 'bodyHead': 'Too many requests'}, True),
        ({'status': 200, 'title': 'Just a moment...', 'bodyHead': ''}, True),
        ({'status': 200, 'title': '', 'bodyHead': 'Security verification'}, True),
        ({'status': 200, 'title': 'Cohiba - LCDH Nyon', 'bodyHead': 'Cohiba products'}, False),
    ],
)
def test_blocked_response_detection(payload, expected):
    assert _is_blocked_response(payload) is expected


def test_nyon_delay_adds_bounded_jitter():
    assert [_nyon_delay_ms(i) for i in range(6)] == [
        8000,
        9700,
        11400,
        13100,
        14800,
        8000,
    ]
