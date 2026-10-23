from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from cigars.models import Brand, Cigar


class StaffCatalogApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Brand.objects.create(english_name='Cohiba', name='高希霸', slug='cohiba')
        cls.cigar = Cigar.objects.create(brand='Cohiba', english_name='Robustos')
        cls.deleted = Cigar.objects.create(brand='Cohiba', english_name='Deleted', deleted_at=timezone.now())
        cls.child = Cigar.objects.create(brand='Cohiba', english_name='Robustos Special', parent=cls.cigar,
                                        deleted_at=timezone.now(), release_type='Special Release')

    def setUp(self):
        self.staff = get_user_model().objects.create_user(username='catalog-staff', is_staff=True)
        self.client.force_login(self.staff)

    def test_missing_and_deleted_entities_return_404(self):
        for path in ['/api/brands/missing/', '/api/cigars/99999/', f'/api/cigars/{self.deleted.pk}/']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_deleted_entries_do_not_appear_in_counts_children_or_related(self):
        listing = self.client.get('/api/brands/').json()
        brand = next(b for section in listing['sections'] for b in section['brands'])
        self.assertEqual(brand['cigar_count'], 1)
        detail = self.client.get('/api/brands/cohiba/').json()
        self.assertEqual(detail['total'], 1)
        cigars = [c for section in detail['sections'] for c in section['cigars']]
        self.assertEqual([c['id'] for c in cigars], [self.cigar.pk])
        self.assertEqual(cigars[0]['children'], [])
        cigar = self.client.get(f'/api/cigars/{self.cigar.pk}/').json()
        self.assertEqual(cigar['brand']['cigar_count'], 1)
        self.assertEqual(cigar['children'], [])
        self.assertEqual(cigar['related'], [])

    def test_related_models_have_a_stable_order_and_limit(self):
        models = [Cigar.objects.create(brand='Cohiba', english_name=f'Model {i:02}') for i in reversed(range(12))]
        path = f'/api/cigars/{self.cigar.pk}/'
        first = self.client.get(path).json()
        self.assertEqual(first, self.client.get(path).json())
        self.assertEqual([c['id'] for c in first['related']], [c.pk for c in reversed(models)][:8])
