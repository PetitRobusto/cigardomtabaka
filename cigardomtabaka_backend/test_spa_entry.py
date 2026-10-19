from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False, SEO_BUILD_DIR="/tmp/cdt-missing-test-build")
class SpaEntryTests(SimpleTestCase):
    def test_startup_loader_does_not_claim_unheld_credential(self):
        response = self.client.get('/')

        self.assertNotContains(response, 'class="cdt-startup__specialist"')
        self.assertNotContains(response, 'alt="Habanos Specialist"')
        self.assertContains(response, '莫斯科雪茄门店')
        self.assertContains(response, 'class="cdt-loading-dots"')
        self.assertContains(response, 'data-motion-src="/static/frontend/logo-opening-motion-v2.svg"')
        self.assertContains(response, 'visibility:hidden;opacity:0')
