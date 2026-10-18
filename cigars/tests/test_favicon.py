from django.test import SimpleTestCase, override_settings


class FaviconTests(SimpleTestCase):
    def test_homepage_declares_png_icon_without_javascript(self):
        for debug in (False, True):
            with self.subTest(debug=debug), override_settings(DEBUG=debug):
                response = self.client.get('/')

                self.assertContains(
                    response,
                    '<link rel="icon" type="image/png" sizes="48x48" '
                    'href="/static/frontend/favicon-48.png">',
                    html=True,
                )

    def test_conventional_icon_urls_redirect_to_images_instead_of_spa(self):
        targets = {
            '/favicon.ico': '/static/frontend/favicon-48.png',
            '/favicon.svg': '/static/frontend/favicon.svg',
        }
        for source, target in targets.items():
            with self.subTest(source=source):
                self.assertRedirects(
                    self.client.get(source), target,
                    status_code=301, fetch_redirect_response=False,
                )
