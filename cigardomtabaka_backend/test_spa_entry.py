from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False)
class SpaEntryTests(SimpleTestCase):
    def test_startup_loader_includes_credential_and_delays_motion_logo(self):
        response = self.client.get('/')

        self.assertContains(response, 'class="cdt-startup__specialist"')
        self.assertContains(response, 'alt="Habanos Specialist"')
        self.assertContains(response, '莫斯科持证雪茄服务商')
        self.assertContains(response, 'class="cdt-loading-dots"')
        self.assertContains(response, 'data-motion-src="/static/frontend/logo-opening-motion-v2.svg"')
        self.assertContains(response, 'visibility:hidden;opacity:0')
