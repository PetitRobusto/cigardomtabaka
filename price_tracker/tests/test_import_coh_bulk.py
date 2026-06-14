"""COH bulk import API tests."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from cigars.models import Brand, Cigar
from price_tracker.models import PriceSnapshot, PriceSource
from price_tracker.views import import_coh_bulk


@pytest.mark.django_db
def test_import_coh_bulk_creates_snapshot_with_box_size():
    """COH import creates a snapshot and parses compound box info."""
    Brand.objects.create(name='Cohiba', english_name='Cohiba')
    cigar = Cigar.objects.create(brand='Cohiba', english_name='Test Robusto')
    source = PriceSource.objects.create(
        name='COH',
        slug='coh',
        base_url='https://coh.example',
        scraper_class='coh',
        currency='USD',
    )
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
    PriceSource.objects.create(
        name='COH',
        slug='coh',
        base_url='https://coh.example',
        scraper_class='coh',
        currency='USD',
    )
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
