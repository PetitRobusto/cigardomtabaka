from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from cigars.models import Brand, Cigar
from price_tracker.models import PriceSource


@override_settings(STOREFRONT_ENABLED=False)
class AdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(english_name='Cohiba', name='高希霸', slug='cohiba')
        cls.cigar = Cigar.objects.create(brand='Cohiba', english_name='Robustos')
        PriceSource.objects.create(
            name='COH', slug='coh', base_url='https://coh.example',
            scraper_class='coh', currency='USD',
        )
        cls.staff = get_user_model().objects.create_user(username='staff', is_staff=True)
        cls.regular = get_user_model().objects.create_user(username='regular')

    def test_catalog_and_inventory_apis_require_staff(self):
        protected_paths = [
            '/api/brands/',
            '/api/brands/cohiba/',
            f'/api/cigars/{self.cigar.pk}/',
            '/api/inventory/',
        ]
        for path in protected_paths:
            with self.subTest(user='anonymous', path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

        self.client.force_login(self.regular)
        for path in protected_paths:
            with self.subTest(user='regular', path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

        self.client.force_login(self.staff)
        expected = [200, 200, 200, 200]
        for path, status_code in zip(protected_paths, expected):
            with self.subTest(user='staff', path=path):
                self.assertEqual(self.client.get(path).status_code, status_code)

    def test_price_tracker_apis_require_staff(self):
        protected_paths = [
            '/api/prices/sources/',
            '/api/prices/snapshots/',
            '/api/prices/alerts/',
        ]
        for path in protected_paths:
            with self.subTest(user='anonymous', path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

        self.client.force_login(self.regular)
        for path in protected_paths:
            with self.subTest(user='regular', path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

        self.client.force_login(self.staff)
        for path in protected_paths:
            with self.subTest(user='staff', path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_management_pages_require_staff_and_customer_pages_remain_open(self):
        staff_pages = [
            '/library/', '/library/brand/cohiba/',
            '/inventory/', '/prices/', '/prices/alerts/', '/privnote/', '/help/',
        ]
        for path in staff_pages:
            with self.subTest(user='anonymous', path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response['Location'].startswith('/login/?next='))

        self.client.force_login(self.regular)
        for path in staff_pages:
            with self.subTest(user='regular', path=path):
                self.assertEqual(self.client.get(path)['Location'], '/')

        self.client.force_login(self.staff)
        for path in staff_pages:
            with self.subTest(user='staff', path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

        self.client.logout()
        self.assertEqual(self.client.get('/p/customer-token/').status_code, 200)
        self.assertNotEqual(self.client.get('/api/privnote/customer-token/').status_code, 403)
