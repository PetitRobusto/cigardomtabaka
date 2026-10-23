import io
from decimal import Decimal

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from cigars.models import Cigar, CigarPrice
from storefront.models import StoreSettings, StoreTranslation


class StoreContentTests(TestCase):
    def test_prepare_is_draft_only_and_preserves_existing_content(self):
        call_command('prepare_storefront_content', dry_run=True, stdout=io.StringIO())
        self.assertFalse(StoreSettings.objects.exists())
        existing = StoreTranslation.objects.create(kind='home', key='home', locale='zh',
            title='用户自写文案', description='用户摘要', body='用户正文', published=True)
        call_command('prepare_storefront_content', stdout=io.StringIO())
        existing.refresh_from_db()
        self.assertEqual(existing.title, '用户自写文案')
        self.assertTrue(existing.published)
        self.assertEqual(StoreTranslation.objects.filter(published=False).count(), 2)
        self.assertFalse(StoreSettings.objects.get(pk=1).details_verified)

    def test_rub_pricing_cannot_be_zero_or_negative_and_keeps_cny(self):
        cigar = Cigar.objects.create(brand='Cohiba', english_name='Robustos')
        price = CigarPrice.objects.create(cigar=cigar, box_size=25, wholesale_price=2000,
                                          retail_price=3000, retail_price_rub=Decimal('12345.67'))
        for invalid in ('0', '-1'):
            with self.assertRaises(IntegrityError), transaction.atomic():
                CigarPrice.objects.filter(pk=price.pk).update(retail_price_rub=Decimal(invalid))
        price.refresh_from_db()
        self.assertEqual(price.wholesale_price, 2000)
        self.assertEqual(price.retail_price, 3000)
        self.assertEqual(price.retail_price_rub, Decimal('12345.67'))
