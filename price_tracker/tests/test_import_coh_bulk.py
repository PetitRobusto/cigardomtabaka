"""COH bulk import API tests."""
import json
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from cigars.models import Brand, Cigar
from price_tracker.coh_import import iter_coh_items
from price_tracker.models import PriceSnapshot, PriceSource
from price_tracker.views import import_coh_bulk


def create_coh_source():
    return PriceSource.objects.create(
        name='COH',
        slug='coh',
        base_url='https://coh.example',
        scraper_class='coh',
        currency='USD',
    )


def write_json(tmp_path, payload):
    json_file = tmp_path / 'coh-prices.json'
    json_file.write_text(json.dumps(payload), encoding='utf-8')
    return json_file


def create_cohiba_cigar(name):
    Brand.objects.get_or_create(name='Cohiba', defaults={'english_name': 'Cohiba'})
    return Cigar.objects.create(brand='Cohiba', english_name=name)


def assert_single_coh_snapshot(cigar, *, price, box_size, product):
    snap = PriceSnapshot.objects.get(cigar=cigar, source__slug='coh')
    assert snap.price == price
    assert snap.price_cny == price * 7.0
    assert snap.box_size == box_size
    assert snap.box_price == price
    assert snap.raw_data['product'] == product
    return snap


def test_iter_coh_items_parses_bulk_and_command_payloads():
    """COH adapter normalizes both browser bulk and command JSON payloads."""
    items, stats = iter_coh_items({
        'cohiba': [
            {'name': 'Test Robusto', 'price': 100, 'box_info': '3x2 Box'},
            {'brand': 'Cohiba', 'product': 'Siglo VI', 'price': 200, 'boxInfo': '25 Box'},
            {'name': 'No Price', 'price': None, 'box_info': '25 Box'},
        ]
    })

    assert stats == {'total': 3, 'skipped_no_price': 1}
    assert [item.name for item in items] == ['Test Robusto', 'Cohiba Siglo VI']
    assert [item.box_size for item in items] == [6, 25]
    assert items[0].raw_data['brand'] == 'Cohiba'
    assert items[0].raw_data['coh_name'] == 'Test Robusto'
    assert items[1].raw_data['product'] == 'Siglo VI'


@pytest.mark.django_db
def test_import_coh_bulk_creates_snapshot_with_box_size():
    """COH import creates a snapshot and parses compound box info."""
    cigar = create_cohiba_cigar('Test Robusto')
    source = create_coh_source()
    user = get_user_model().objects.create_user(username='coh-importer')
    request = APIRequestFactory().post(
        '/api/prices/import_coh/',
        {'cohiba': [{'name': 'Test Robusto', 'price': 100, 'box_info': '3x2 Box'}]},
        format='json',
    )
    force_authenticate(request, user=user)

    response = import_coh_bulk(request)

    assert response.status_code == 200
    assert response.data['ok'] is True
    assert response.data['total'] == 1
    assert response.data['matched'] == 1
    assert response.data['created'] == 1
    snap = PriceSnapshot.objects.get(source=source, cigar=cigar)
    assert snap.box_size == 6
    assert snap.box_price == 100
    assert snap.raw_data['coh_name'] == 'Test Robusto'
    assert snap.raw_data['box_info'] == '3x2 Box'


@pytest.mark.django_db
def test_import_coh_bulk_reports_unmatched_and_price_skips():
    """COH import keeps skipped no-price rows separate from unmatched rows."""
    Brand.objects.create(name='Cohiba', english_name='Cohiba')
    create_coh_source()
    user = get_user_model().objects.create_user(username='coh-importer')
    request = APIRequestFactory().post(
        '/api/prices/import_coh/',
        {
            'cohiba': [
                {'name': 'No Price Cigar', 'price': None, 'box_info': '25 Box'},
                {'name': 'Definitely Unknown', 'price': 100, 'box_info': '25 Box'},
            ]
        },
        format='json',
    )
    force_authenticate(request, user=user)

    response = import_coh_bulk(request)

    assert response.status_code == 200
    assert response.data['ok'] is True
    assert response.data['total'] == 2
    assert response.data['matched'] == 0
    assert response.data['created'] == 0
    assert response.data['skipped'] == 2
    assert response.data['unmatched_count'] == 1
    assert response.data['unmatched'] == ['Cohiba: Definitely Unknown']
    assert PriceSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_import_coh_prices_command_uses_ingestion_and_dedupes(tmp_path):
    """Legacy COH command payloads go through ingestion and inherit deduping."""
    cigar = create_cohiba_cigar('Command Robusto')
    create_coh_source()
    json_file = write_json(tmp_path, {
        'cohiba': [
            {
                'brand': 'Cohiba',
                'product': 'Command Robusto',
                'price': 123,
                'boxInfo': '25 Box',
            }
        ]
    })

    out = StringIO()
    call_command('import_coh_prices', str(json_file), stdout=out)
    call_command('import_coh_prices', str(json_file), stdout=out)

    assert_single_coh_snapshot(
        cigar,
        price=123,
        box_size=25,
        product='Command Robusto',
    )
    assert PriceSnapshot.objects.count() == 1
    assert '新增: 1' in out.getvalue()
    assert '新增: 0' in out.getvalue()


@pytest.mark.django_db
def test_import_coh_full_command_uses_base_command_ingestion(tmp_path):
    """Full-site browser scrape exports use the same COH adapter and ingestion path."""
    cigar = create_cohiba_cigar('Full Robusto')
    create_coh_source()
    json_file = write_json(tmp_path, {
        'cohiba': [
            {'name': 'Full Robusto', 'price': 234, 'box_info': '3x2 Box'},
        ],
    })

    out = StringIO()
    call_command('import_coh_full', str(json_file), stdout=out)

    assert_single_coh_snapshot(
        cigar,
        price=234,
        box_size=6,
        product='Full Robusto',
    )
    assert '新增: 1' in out.getvalue()


@pytest.mark.django_db
def test_import_coh_prices_dry_run_does_not_write(tmp_path):
    """Dry-run parses command payloads without creating snapshots."""
    create_cohiba_cigar('Dry Run Robusto')
    create_coh_source()
    json_file = write_json(tmp_path, {
        'cohiba': [
            {
                'brand': 'Cohiba',
                'product': 'Dry Run Robusto',
                'price': 88,
                'boxInfo': '10 Box',
            }
        ]
    })

    out = StringIO()
    call_command('import_coh_prices', str(json_file), dry_run=True, stdout=out)

    assert PriceSnapshot.objects.count() == 0
    assert '待导入: 1' in out.getvalue()
