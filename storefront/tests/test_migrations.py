"""New public-price fields must preserve existing CNY quotes and rate history."""
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, tag


@tag('migration', 'migration-other')
class StorefrontSchemaMigrationTests(TransactionTestCase):
    def test_existing_prices_and_rates_survive_without_invented_public_values(self):
        before = [
            ('cigars', '0045_sales_preorder_source'),
            ('price_tracker', '0009_alter_pricesnapshot_scraped_date'),
        ]
        after = [
            ('cigars', '0046_cigarprice_retail_price_rub_and_more'),
            ('price_tracker', '0010_exchangerate_source_updated_at'),
        ]
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(leaves))
        executor.migrate(before)
        old_apps = MigrationExecutor(connection).loader.project_state(before).apps
        cigar = old_apps.get_model('cigars', 'Cigar').objects.create(
            brand='Cohiba', english_name='Migration sample',
        )
        old_price = old_apps.get_model('cigars', 'CigarPrice').objects.create(
            cigar_id=cigar.pk, box_size=25, wholesale_price=2000,
            retail_price=3000, is_active=True, can_preorder=True, sort_order=4,
        )
        old_rate = old_apps.get_model('price_tracker', 'ExchangeRate').objects.create(
            currency='USD', rate=7.1234,
        )
        price_snapshot = old_apps.get_model('cigars', 'CigarPrice').objects.values().get(pk=old_price.pk)
        rate_snapshot = old_apps.get_model('price_tracker', 'ExchangeRate').objects.values().get(pk=old_rate.pk)

        MigrationExecutor(connection).migrate(after)
        apps = MigrationExecutor(connection).loader.project_state(after).apps
        prices = apps.get_model('cigars', 'CigarPrice')
        rates = apps.get_model('price_tracker', 'ExchangeRate')
        self.assertEqual(prices.objects.values(*price_snapshot).get(pk=old_price.pk), price_snapshot)
        self.assertEqual(rates.objects.values(*rate_snapshot).get(pk=old_rate.pk), rate_snapshot)
        self.assertIsNone(prices.objects.get(pk=old_price.pk).retail_price_rub)
        self.assertIsNone(rates.objects.get(pk=old_rate.pk).source_updated_at)

        for invalid in (Decimal('0'), Decimal('-1')):
            with self.subTest(price=invalid), self.assertRaises(IntegrityError), transaction.atomic():
                prices.objects.filter(pk=old_price.pk).update(retail_price_rub=invalid)
        prices.objects.filter(pk=old_price.pk).update(retail_price_rub=Decimal('12345.67'))
        self.assertEqual(prices.objects.get(pk=old_price.pk).retail_price_rub, Decimal('12345.67'))
        self.assertEqual(prices.objects.values(*price_snapshot).get(pk=old_price.pk), price_snapshot)
