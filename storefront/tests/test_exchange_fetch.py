import io
import json
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from price_tracker.models import ExchangeRate


class ExchangeFetchTests(TestCase):
    def test_rub_fetch_keeps_source_timestamp_and_updates_same_day(self):
        source_time = int(timezone.now().timestamp()) - 3600
        def response(*args, **kwargs):
            return io.BytesIO(json.dumps({'rates': {'CNY': 0.08333333}, 'time_last_update_unix': source_time}).encode())
        with patch('urllib.request.urlopen', side_effect=response):
            errors = io.StringIO()
            call_command('fetch_exchange_rates', stdout=io.StringIO(), stderr=errors)
            call_command('fetch_exchange_rates', stdout=io.StringIO(), stderr=errors)
        self.assertEqual(errors.getvalue(), '')
        self.assertEqual(ExchangeRate.objects.count(), 4)
        rub = ExchangeRate.objects.get(currency='RUB')
        self.assertAlmostEqual(rub.rate, 0.08333333)
        self.assertEqual(int(rub.source_updated_at.timestamp()), source_time)

    def test_invalid_source_never_replaces_valid_data(self):
        ExchangeRate.objects.create(currency='RUB', rate=0.08, source_updated_at=timezone.now())
        def response(*args, **kwargs):
            return io.BytesIO(b'{"rates":{"CNY":-1}}')
        with patch('urllib.request.urlopen', side_effect=response):
            call_command('fetch_exchange_rates', stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(ExchangeRate.objects.get(currency='RUB').rate, 0.08)
