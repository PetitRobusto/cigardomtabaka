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
        self.listing = ProductListing.objects.create(cigar=self.cigar, published=True)
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
        self.assertEqual([product['id'] for product in brand['products']], [self.cigar.pk])
        self.assertNotIn('model_articles', brand)
        self.assertIn(['product', str(self.cigar.pk), 'en'], brand['translation_dependencies'])
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
        self.listing.published = False
        self.listing.withdrawn = True
        self.listing.save(update_fields=['published', 'withdrawn'])
        self.assertFalse(allowed_payload(cached))
        self.listing.delete()
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

    def test_published_product_keeps_brand_landing_without_brand_body(self):
        StoreTranslation.objects.filter(kind='brand').update(body='')
        self.translation('en', published=True)
        self.translation('zh', published=True)
        pages = build_pages()
        for prefix in ('', '/ru', '/en'):
            self.assertEqual([item['id'] for item in pages[prefix + '/brand/cohiba']['products']], [self.cigar.pk])
            self.assertTrue(allowed_payload(pages[prefix + '/brand/cohiba']))

    def test_exact_empty_brand_body_does_not_borrow_english_copy(self):
        for locale in ('zh', 'ru', 'en'):
            self.translation(locale, published=True)
        cached = build_pages()['/brand/cohiba']
        StoreTranslation.objects.filter(kind='brand', locale='ru').update(body='')
        russian = build_pages()['/ru/brand/cohiba']
        self.assertEqual(russian['body'], '')
        self.assertNotIn('Reviewed body', russian['body'])
        self.assertTrue(allowed_payload(cached))

    def test_each_published_language_uses_own_override_without_changing_content(self):
        titles = {'zh': '高希霸天才：莫斯科', 'ru': 'Cohiba Genios в Москве', 'en': 'Cohiba Genios in Moscow'}
        for locale, title in titles.items():
            self.translation(locale, seo_title=title, published=True)
        for page in build_pages().values():
            if page['kind'] != 'product':
                continue
            self.assertEqual(page['title'], 'Genios')
            self.assertEqual(page['product']['name'], 'Genios')
            self.assertEqual(page['description'], 'Reviewed model summary')
            self.assertEqual(page['seo_title'], titles[page['locale']] + ' | CigarDomTabaka')
            self.assertEqual(page, build_pages(requested_path=page['path'])[page['path']])

    def test_override_follows_resolved_published_translation_and_never_draft(self):
        en = self.translation('en', seo_title='Approved English search title', published=True)
        self.translation('ru', seo_title='SECRET draft title', published=False)
        self.translation('zh', seo_title='SECRET Chinese draft', published=False)
        pages = {p['locale']: p for p in build_pages().values() if p['kind'] == 'product'}
        self.assertEqual(pages['ru']['seo_title'], 'Approved English search title | CigarDomTabaka')
        self.assertFalse(pages['ru']['translation_complete'])
        self.assertFalse(pages['ru']['indexable'])
        self.assertIn(['product', str(self.cigar.pk), 'en'], pages['ru']['translation_dependencies'])
        self.assertEqual(pages['zh']['seo_title_override'], '')
        self.assertNotIn('SECRET', repr(pages))
        StoreTranslation.objects.filter(pk=en.pk).update(published=False)
        for page in build_pages().values():
            if page['kind'] == 'product':
                self.assertEqual(page['seo_title_override'], '')

    def test_home_and_brand_override_and_admin_editing(self):
        from cigars.admin import ProductTranslationForm, ProductTranslationInline
        from django.contrib.admin import site
        from django.test import RequestFactory
        from storefront.admin import StoreTranslationAdmin

        StoreTranslation.objects.filter(kind='home', locale='en').update(seo_title='Home search title')
        StoreTranslation.objects.filter(kind='brand', locale='en').update(seo_title='Brand search title')
        pages = build_pages()
        self.assertEqual(pages['/en/']['seo_title'], 'Home search title | CigarDomTabaka')
        self.assertEqual(pages['/en/brand/cohiba']['seo_title'], 'Brand search title | CigarDomTabaka')
        self.assertEqual(pages['/en/catalog']['seo_title'], 'Cigar catalogue | CigarDomTabaka')
        form = ProductTranslationForm()
        self.assertIn('seo_title', ProductTranslationInline.fields)
        self.assertFalse(form.fields['seo_title'].required)
        self.assertIn('[文字](https://...)', form.fields['body'].help_text)
        admin = StoreTranslationAdmin(StoreTranslation, site)
        field = admin.formfield_for_dbfield(StoreTranslation._meta.get_field('body'), RequestFactory().get('/'))
        self.assertIn('[文字](https://...)', field.help_text)

    def test_override_length_is_validated_without_making_it_required(self):
        row = self.translation(published=True)
        row.full_clean()
        row.seo_title = 'x' * 181
        with self.assertRaises(ValidationError) as error:
            row.full_clean()
        self.assertIn('seo_title', error.exception.message_dict)
