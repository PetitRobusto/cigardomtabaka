"""Exercise the real CI-built React renderer against Django's public contract."""
import shutil
import mimetypes
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless
from urllib.parse import urlsplit

from django.conf import settings
from django.test import TestCase, override_settings

from cigars.models import Brand, Cigar, CigarImage, CigarPrice
from cigars.tests.inventory_fixtures import create_purchase_batch
from storefront.models import ProductListing, StorePage, StoreSettings, StoreTranslation
from storefront.publishing import build_assets, publish_pending, reconcile
from deploy.verify_storefront_http import Response, audit


@skipUnless(shutil.which('node') and Path(settings.STOREFRONT_RENDERER).is_file(), 'Run npm run build to exercise the real React renderer')
@override_settings(STOREFRONT_ENABLED=True, STOREFRONT_ORIGIN='https://store.example')
class PrerenderIntegrationTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(english_name='Cohiba', name='高希霸', slug='cohiba')
        self.cigar = Cigar.objects.create(brand='Cohiba', english_name='Robustos', name='罗布图', length=124, ring_gauge=50,
                                          image_url='https://images.example/robustos.jpg')
        self.box_image = CigarImage.objects.create(
            cigar=self.cigar, image='cigars/robustos-box-25.jpg',
            image_type='packaging', box_size=25,
        )
        create_purchase_batch(source='opening', cigar=self.cigar, quantity=25, remaining=25, physical_remaining=25,
                              box_size=25, unit_cost_cny=Decimal('1.00'))
        self.listing = ProductListing.objects.create(cigar=self.cigar, published=True)
        CigarPrice.objects.create(cigar=self.cigar, box_size=25, wholesale_price=100, retail_price_rub=Decimal('12345.67'))
        StoreSettings.objects.create(details_verified=True, address='Moscow', phone='+7 999 000 0000', wechat='test-wechat')
        for locale, title in [('zh', '莫斯科雪茄现货'), ('ru', 'Сигары в Москве'), ('en', 'Cigars in Moscow')]:
            for kind, key in [('home', 'home'), ('brand', self.brand.slug), ('product', str(self.cigar.pk))]:
                StoreTranslation.objects.create(kind=kind, key=key, locale=locale, title=title,
                    description=f'{title} — Cohiba Robustos', body=f'{title}: original complete product information.', published=True)
        self.assets = build_assets()
        reconcile(assets=self.assets)
        self.assertEqual(publish_pending(assets=self.assets), 12)

    def test_full_anonymous_html_and_language_routes(self):
        for locale, path in [('zh', '/'), ('ru', '/ru/'), ('en', '/en/'),
                             ('zh', '/catalog'), ('ru', '/ru/catalog'), ('en', '/en/catalog')]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '<h1')
            self.assertContains(response, '12345.67')
            self.assertContains(response, 'RUB ₽')
            self.assertContains(response, 'id="store-data"')
            self.assertContains(response, 'rel="canonical"')
            self.assertContains(response, 'hreflang="ru"')
            self.assertContains(response, 'data-age-gate')
            self.assertContains(response, 'data-age-confirm')
            self.assertContains(response, 'src="/media/cigars/robustos-box-25.jpg"')
            self.assertNotContains(response, 'src="https://images.example/robustos.jpg"')
            if path.endswith('catalog'):
                prefix = '' if locale == 'zh' else f'/{locale}'
                self.assertContains(response, f'href="{prefix}/cigar/{self.cigar.pk}/cohiba-robustos?from=')
            # Public pages retain one header/footer without specialist credentials.
            self.assertNotContains(response, 'Habanos Specialist')
            self.assertNotContains(response, 'habanos-specialist.png')
            self.assertNotContains(response, 'site-footer-credential')
            self.assertContains(response, '<header ', count=1)
            self.assertContains(response, '<footer ', count=1)
            self.assertNotContains(response, 'id="site-management-menu"')
            self.assertNotContains(response, 'class="site-staff-dock"')
            self.assertNotContains(response, 'unit_cost_cny')
            self.assertEqual(self.client.head(path).content, b'')
            self.assertEqual(self.client.get(path, HTTP_IF_NONE_MATCH=response['ETag']).status_code, 304)
        product = self.client.get(f'/en/cigar/{self.cigar.pk}/cohiba-robustos')
        self.assertEqual(product.status_code, 200)
        self.assertContains(product, '<h1>Cigars in Moscow</h1>')
        self.assertContains(product, 'original complete product information.')
        self.assertContains(product, 'RUB ₽')
        self.assertContains(product, 'data-price-rub="12345.67"')
        self.assertContains(product, 'src="/media/cigars/robustos-box-25.jpg"')
        self.assertContains(product, 'data-age-gate="true"')
        self.assertContains(product, 'href="/en/catalog"')
        sitemap = self.client.get('/sitemap-storefront.xml')
        self.assertContains(sitemap, 'https://store.example/en/')
        self.assertContains(self.client.get('/robots.txt'), 'https://store.example/sitemap-storefront.xml')

    def test_old_link_redirect_search_noindex_and_real_404(self):
        old = f'/cigar/{self.cigar.pk}/old-name'
        response = self.client.get(old)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], f'/cigar/{self.cigar.pk}/cohiba-robustos')
        self.assertEqual(self.client.get('/?q=Cohiba')['X-Robots-Tag'], 'noindex, nofollow')
        self.assertEqual(self.client.get('/en/not-a-page').status_code, 404)
        self.assertEqual(self.client.get('/ru/catalog/not-a-page').status_code, 404)
        self.assertEqual(self.client.get('/invented-page').status_code, 404)

    def test_release_http_audit_accepts_real_rendered_pages_and_public_sitemap(self):
        def request(url):
            parsed = urlsplit(url)
            if parsed.path.startswith('/static/frontend/'):
                path = Path(settings.STOREFRONT_RENDERER).parent.parent / parsed.path.removeprefix('/static/frontend/')
                return Response(200, {'content-type': mimetypes.guess_type(path)[0]},
                                path.read_bytes().decode('utf-8', errors='replace'))
            response = self.client.get(parsed.path + ('?' + parsed.query if parsed.query else ''))
            return Response(response.status_code, {key.lower(): value for key, value in response.items()},
                            response.content.decode())

        report = audit(settings.STOREFRONT_ORIGIN, request=request,
                       extra_paths=['/catalog', '/ru/brand/cohiba', f'/en/cigar/{self.cigar.pk}/cohiba-robustos'])
        self.assertTrue(report['ready'], report['issues'])
        self.assertEqual(report['sitemap_url_count'], 12)

    def test_unknown_box_size_is_not_presented_as_the_25_cigar_offer_photo(self):
        self.box_image.box_size = None
        self.box_image.save(update_fields=['box_size'])
        reconcile(assets=self.assets)
        self.assertEqual(publish_pending(assets=self.assets), 12)
        for path in ['/', '/catalog', f'/en/cigar/{self.cigar.pk}/cohiba-robustos']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'store-image-placeholder')
            self.assertNotContains(response, 'src="/media/cigars/robustos-box-25.jpg"')
            self.assertNotContains(response, 'src="https://images.example/robustos.jpg"')

    def test_withdrawn_product_is_not_served_from_previous_html(self):
        self.listing.published = False
        self.listing.withdrawn = True
        self.listing.save()
        product_path = f'/cigar/{self.cigar.pk}/cohiba-robustos'
        self.assertEqual(self.client.get(product_path).status_code, 404)
        self.assertEqual(self.client.get('/').status_code, 503)
        self.assertNotContains(self.client.get('/sitemap-storefront.xml'), product_path)

    def test_cache_refresh_preserves_rendering_without_waiting_for_login(self):
        row = StorePage.objects.get(path='/en/')
        self.assertNotIn('/api/auth/me/', row.html)
        self.assertIn('original complete product information', row.html)
