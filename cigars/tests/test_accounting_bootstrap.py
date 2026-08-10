from django.apps import apps
from django.test import SimpleTestCase


class AccountingBootstrapTest(SimpleTestCase):
    def test_accounting_app_is_installed(self):
        self.assertTrue(apps.is_installed('accounting'))
