from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from cigars.models import Brand, Cigar
from storefront.catalog import allowed_payload, build_pages, public_dependencies
from storefront.models import ProductListing, StoreTranslation


class ProductTranslationTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(english_name='Cohiba', slug='cohiba')
        self.cigar = Cigar.objects.create(brand='Cohiba', english_name='Genios')
        for locale in ('zh', 'ru', 'en'):
            for kind, key in [('home', 'home'), ('brand', 'cohiba')]:
                StoreTranslation.objects.create(kind=kind, key=key, locale=locale,
                    title='Reviewed title', description='Reviewed summary', body='Reviewed body', published=True)

    def translation(self, locale='en', **kwargs):
        return StoreTranslation.objects.create(kind='product', cigar=self.cigar, locale=locale,
            title='Genios', description='Reviewed model summary', body='Reviewed model body', **kwargs)

    def test_legacy_key_and_fk_writes_share_one_identity(self):
        row = StoreTranslation(kind='product', key=str(self.cigar.pk), locale='en', title='Genios',
                               description='Summary', body='Body')
        row.full_clean()
        row.save()
        row.title = 'Updated title'
        row.save(update_fields=['title'])
        self.assertEqual(self.cigar.store_translations.get().cigar_id, self.cigar.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.translation()
        row.key = '999'
        with self.assertRaises(ValidationError):
            row.save(update_fields=['title'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            StoreTranslation.objects.filter(pk=row.pk).update(key='999')
        with self.assertRaises(ValidationError):
            StoreTranslation(kind='brand', key='cohiba', cigar=self.cigar).save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            StoreTranslation.objects.filter(pk=row.pk).update(cigar=None)

    def test_database_copy_is_on_product_page_without_duplicate_brand_section(self):
        self.translation(published=True)
        pages = build_pages()
        page = next(page for page in pages.values() if page['kind'] == 'product' and page['locale'] == 'en')
        self.assertEqual(page['body'], 'Reviewed model body')
        self.assertEqual(page, build_pages(requested_path=page['path'])[page['path']])
        brand = pages['/en/brand/cohiba']
        self.assertEqual(brand['products'], [])
        self.assertNotIn('model_articles', brand)
        self.assertNotIn(['product', str(self.cigar.pk), 'en'], brand['translation_dependencies'])
        dependencies = public_dependencies()
        for path, payload in pages.items():
            self.assertTrue(allowed_payload(payload, dependencies), path)
        stale = deepcopy(brand)
        stale['model_articles'] = [page['product']]
        self.assertFalse(allowed_payload(stale))

    def test_cancel_publish_withdraw_and_delete_invalidate_product_copy(self):
        row = self.translation(published=True)
        cached = next(page for page in build_pages().values() if page['kind'] == 'product' and page['locale'] == 'en')
        StoreTranslation.objects.filter(pk=row.pk).update(published=False)
        self.assertFalse(allowed_payload(cached))
        StoreTranslation.objects.filter(pk=row.pk).update(published=True)
        listing = ProductListing.objects.create(cigar=self.cigar, withdrawn=True)
        self.assertFalse(allowed_payload(cached))
        listing.delete()
        Cigar.objects.filter(pk=self.cigar.pk).update(deleted_at=timezone.now())
        self.assertFalse(allowed_payload(cached))

    def test_inline_reports_deleted_product_without_missing_field_exception(self):
        from cigars.admin import ProductTranslationForm
        row = self.translation(published=True)
        Cigar.objects.filter(pk=self.cigar.pk).update(deleted_at=timezone.now())
        form = ProductTranslationForm(data={'locale': 'en', 'title': 'Genios', 'description': 'Summary',
                                           'body': 'Body', 'aliases': '', 'published': True}, instance=row)
        self.assertFalse(form.is_valid())
        self.assertIn('关联商品不存在或已删除', str(form.non_field_errors()))

    def test_product_copy_does_not_make_an_empty_brand_indexable(self):
        StoreTranslation.objects.filter(kind='brand').update(body='')
        self.translation('en', published=True)
        self.translation('zh', published=True)
        pages = build_pages()
        for prefix in ('', '/ru', '/en'):
            self.assertFalse(pages[prefix + '/brand/cohiba']['indexable'])
            self.assertTrue(allowed_payload(pages[prefix + '/brand/cohiba']))

    def test_exact_empty_brand_body_does_not_borrow_english_body_for_hreflang(self):
        cached = build_pages()['/brand/cohiba']
        self.assertIn('ru', [row['locale'] for row in cached['alternates']])
        StoreTranslation.objects.filter(kind='brand', locale='ru').update(body='')
        self.assertFalse(build_pages()['/ru/brand/cohiba']['indexable'])
        self.assertFalse(allowed_payload(cached))
