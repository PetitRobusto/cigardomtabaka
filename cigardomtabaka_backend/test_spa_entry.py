from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False)
class SpaEntryTests(SimpleTestCase):
    def test_startup_loader_omits_specialist_logo_and_delays_motion_logo(self):
        response = self.client.get('/')

        self.assertNotContains(response, 'cdt-startup__specialist')
        self.assertNotContains(response, 'habanos-specialist.png')
        self.assertNotContains(response, '莫斯科持证雪茄服务商')
        self.assertContains(response, '页面内容加载中…')
        self.assertContains(response, 'class="cdt-loading-dots"')
        self.assertContains(response, 'data-motion-src="/static/frontend/logo-opening-motion-v2.svg"')
        self.assertContains(response, 'visibility:hidden;opacity:0')
