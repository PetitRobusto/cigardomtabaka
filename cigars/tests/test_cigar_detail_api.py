import json

from django.test import TestCase

from cigars.models import Cigar


class CigarDetailPackagingApiTest(TestCase):
    def test_detail_exposes_declared_box_sizes_separately_from_display_packagings(self):
        cigar = Cigar.objects.create(
            brand='包装接口品牌',
            english_name='Packaging API Cigar',
            name='包装接口雪茄',
            packagings=json.dumps({
                'box_sizes': [10, 25],
                'raw': 'Box of 25. Box of 10.',
            }),
        )

        response = self.client.get(f'/api/cigars/{cigar.pk}/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()['cigar']
        self.assertEqual(payload['box_sizes'], [10, 25])
        # Human-facing packaging descriptions remain a separate compatibility field.
        self.assertEqual(len(payload['packagings']), 2)
