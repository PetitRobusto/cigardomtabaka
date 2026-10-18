from collections import Counter

from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner
from django.test.utils import iter_test_cases


class CiPartitionTests(SimpleTestCase):
    def test_backend_groups_cover_every_test_exactly_once(self):
        labels = ['cigars', 'privnote', 'accounting', 'cigardomtabaka_backend']

        def discover(**options):
            return list(iter_test_cases(DiscoverRunner(verbosity=0, **options).build_suite(labels)))

        full = discover()
        groups = [
            discover(exclude_tags={'migration'}),
            discover(tags={'migration-inventory'}),
            discover(tags={'migration-other'}),
        ]
        self.assertTrue(all(groups), 'A CI test group is empty')
        self.assertEqual(
            Counter(test.id() for group in groups for test in group),
            Counter(test.id() for test in full),
            'CI groups must cover every discovered test exactly once',
        )
        for test in full:
            if 'Migration' in type(test).__name__:
                self.assertIn('migration', getattr(test, 'tags', set()), test.id())
