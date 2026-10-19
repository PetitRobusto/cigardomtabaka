from django.conf import settings
from django.test import SimpleTestCase, override_settings
from PIL import Image


@override_settings(SEO_BUILD_DIR='/tmp/cdt-missing-favicon-build')
class FaviconTests(SimpleTestCase):
    def test_homepage_declares_png_icon_without_javascript(self):
        for debug in (False, True):
            with self.subTest(debug=debug), override_settings(DEBUG=debug):
                response = self.client.get('/')

                self.assertContains(
                    response,
                    '<link rel="icon" type="image/png" sizes="96x96" '
                    'href="/static/frontend/favicon-96.png">',
                    html=True,
                )

    def test_conventional_icon_urls_redirect_to_images_instead_of_spa(self):
        targets = {
            '/favicon.ico': '/static/frontend/favicon.ico',
            '/favicon.svg': '/static/frontend/favicon.svg',
        }
        for source, target in targets.items():
            with self.subTest(source=source):
                self.assertRedirects(
                    self.client.get(source), target,
                    status_code=301, fetch_redirect_response=False,
                )

    def test_png_icons_have_transparent_background_and_fill_the_canvas(self):
        for size in (48, 96):
            with self.subTest(size=size):
                path = settings.BASE_DIR / 'frontend' / 'public' / f'favicon-{size}.png'
                with Image.open(path) as icon:
                    self.assertEqual(icon.size, (size, size))
                    alpha = icon.convert('RGBA').getchannel('A')
                    minimum, maximum = alpha.getextrema()
                    self.assertEqual(minimum, 0)
                    self.assertGreaterEqual(maximum, 240)
                    self.assertEqual(alpha.getpixel((0, 0)), 0)
                    bounds = alpha.point(lambda value: 255 if value >= 32 else 0).getbbox()
                    self.assertIsNotNone(bounds)
                    left, top, right, bottom = bounds
                    self.assertGreaterEqual(right - left, size * 0.9)
                    self.assertGreaterEqual(bottom - top, size * 0.75)
