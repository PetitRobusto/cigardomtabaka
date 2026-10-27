import json
from copy import deepcopy
from unittest.mock import patch

from django.core.management import CommandError
from django.test import SimpleTestCase

from storefront.content_release import CONTENT_DIR, read_release


class CatalogReleaseManifestTests(SimpleTestCase):
    def setUp(self):
        self.documents = {path.name: json.loads(path.read_text()) for path in CONTENT_DIR.glob('*.json')}

    def read(self):
        with patch('storefront.content_release._read', side_effect=lambda name: self.documents[name]):
            return read_release()

    def test_complete_reviewed_scope_and_homonymous_products(self):
        scope, products, brands = self.read()
        self.assertEqual((len(products), len(brands)), (60, 20))
        self.assertEqual({pk for pk, e in products.items() if e['decision'] == 'preserve'}, {97, 98, 102})
        self.assertEqual([key for key, e in brands.items() if e['decision'] == 'preserve'], ['cohiba'])
        self.assertEqual(products[1212]['verified_specs'], {'length': None, 'ring_gauge': None, 'vitola': ''})
        self.assertEqual(scope['spec_corrections']['893']['length'], 124)
        for locale in ('zh', 'ru', 'en'):
            for field in ('description', 'body'):
                self.assertIn('Partagás', products[599]['translations'][locale][field])
                self.assertNotIn('Romeo', products[599]['translations'][locale][field])
                self.assertIn('Romeo', products[979]['translations'][locale][field])

    def test_missing_language_or_unapproved_copy_field_is_rejected(self):
        entry = self.documents['seo18-products-a.json']['products'][0]
        original = deepcopy(entry['translations'])
        del entry['translations']['en']
        with self.assertRaisesMessage(CommandError, '中俄英三语'):
            self.read()
        entry['translations'] = original
        entry['translations']['en']['title'] = 'Unapproved rename'
        with self.assertRaisesMessage(CommandError, '只允许'):
            self.read()

    def test_russian_and_english_copy_do_not_contain_chinese_translation(self):
        _, products, brands = self.read()
        for entry in [*products.values(), *brands.values()]:
            for locale in ('ru', 'en'):
                for field, value in entry['translations'][locale].items():
                    with self.subTest(key=entry.get('id', entry.get('slug')), locale=locale, field=field):
                        self.assertNotRegex(value, r'[\u3400-\u9fff]')
                        if locale == 'ru':
                            self.assertRegex(value, r'[А-Яа-яЁё]')

    def test_duplicate_identity_and_brand_mismatch_are_rejected(self):
        entries = self.documents['seo18-products-a.json']['products']
        entries.append(deepcopy(entries[0]))
        with self.assertRaisesMessage(CommandError, '重复'):
            self.read()
        entries.pop()
        entries[0]['brand_slug'] = 'partagas'
        with self.assertRaisesMessage(CommandError, '品牌关联'):
            self.read()

    def test_unapproved_numeric_and_factory_name_changes_are_rejected(self):
        entry = self.documents['seo18-products-a.json']['products'][0]
        for field, value in [('length', 999), ('vitola', 'Another factory vitola')]:
            original = deepcopy(entry['verified_specs'])
            entry['verified_specs'][field] = value
            with self.assertRaisesMessage(CommandError, '已核实规格与批准修正不一致'):
                self.read()
            entry['verified_specs'] = original
        self.documents['seo18-scope.json']['spec_corrections']['93']['name'] = 'Unapproved rename'
        with self.assertRaisesMessage(CommandError, '规格之外'):
            self.read()

    def test_unreviewed_or_missing_inline_sources_are_rejected(self):
        entry = next(e for e in self.documents['seo18-products-a.json']['products'] if e['decision'] == 'update')
        for body in ('No source', 'Claim [source](https://unreviewed.example/source)'):
            entry['translations']['en']['body'] = body
            with self.assertRaisesMessage(CommandError, '已核对的来源'):
                self.read()

    def test_blocked_identity_and_credential_source_are_rejected(self):
        entry = self.documents['seo18-products-a.json']['products'][0]
        decision = entry['decision']
        entry['decision'] = 'blocked'
        with self.assertRaisesMessage(CommandError, '尚未解决'):
            self.read()
        entry['decision'] = decision
        entry['sources'][0]['url'] = 'https://user:secret@example.com/'
        with self.assertRaisesMessage(CommandError, 'HTTPS'):
            self.read()
