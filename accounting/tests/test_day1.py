from datetime import date, timedelta
from decimal import Decimal
import json
import threading

from django.db import (
    IntegrityError, OperationalError, close_old_connections, transaction,
)
from django.test import Client, TestCase, TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from unittest.mock import patch
from importlib import import_module

from accounting.models import (
    Day1Initialization, FundAccount, LedgerPosting, LedgerTransaction,
)
from accounting.business_time import moscow_business_date
from accounting.selectors import account_snapshot
from accounting.services import CUTOVER_DATE, LedgerError, PostingInput, post_transaction
from cigars.models import StockMovement
from cigars.models import Cigar, PurchaseBatch, PurchaseOrder, PurchaseOrderItem, Supplier, User
from cigars.tests.inventory_fixtures import (
    create_purchase_batch, create_stock_movement, force_create_purchase_batch,
)


class Day1ServiceTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            'day1-service-operator', is_staff=True,
        )
        self.partner = User.objects.create_user(
            'day1-service-partner', is_staff=True,
        )
        self.cigar = Cigar.objects.create(
            brand='Day 1 Service Brand', english_name='Day 1 Service Cigar', name='期初服务雪茄',
        )

    def payload(self, *, name='老板人民币', loose_sticks=2):
        return {
            'business_date': date(2026, 8, 13),
            'accounts': [
                {'slot': 'owner_cny', 'name': name, 'currency': 'CNY', 'original_amount': '100.00', 'cny_book_cost': '100.00'},
                {'slot': 'partner_cny', 'name': '合伙人人民币', 'currency': 'CNY', 'original_amount': '0.00', 'cny_book_cost': '0.00'},
                {'slot': 'rub', 'name': '卢布账户', 'currency': 'RUB', 'original_amount': '1200.00', 'cny_book_cost': '100.00'},
                {'slot': 'usdt', 'name': 'USDT账户', 'currency': 'USDT', 'original_amount': '10.00000000', 'cny_book_cost': '70.00'},
            ],
            'inventory': [
                {'cigar_id': self.cigar.pk, 'box_size': 25, 'box_quantity': 1, 'loose_sticks': loose_sticks, 'unit_cost_cny': '12.50'},
            ],
        }

    def save_draft(self, payload=None):
        from accounting.day1 import save_day1_draft
        return save_day1_draft(
            payload=payload or self.payload(), expected_version=0, operator=self.operator,
        )

    def confirm(self, draft, *, key='day1-confirm', operator=None, version=None):
        from accounting.day1 import confirm_day1
        return confirm_day1(
            expected_version=draft.version if version is None else version,
            operator=operator or self.operator,
            idempotency_key=key,
        )

    def generated_counts(self):
        return (
            FundAccount.objects.count(), LedgerTransaction.objects.count(),
            LedgerPosting.objects.count(), PurchaseBatch.objects.count(),
            StockMovement.objects.count(),
        )

    def test_shared_draft_uses_optimistic_version_and_replaces_payload(self):
        from accounting.day1 import Day1VersionConflict, save_day1_draft

        first = save_day1_draft(
            payload=self.payload(), expected_version=0, operator=self.operator,
        )
        self.assertEqual(first.version, 1)
        self.assertEqual(Day1Initialization.objects.count(), 1)

        with self.assertRaises(Day1VersionConflict):
            save_day1_draft(
                payload=self.payload(name='不应覆盖'), expected_version=0,
                operator=self.partner,
            )
        first.refresh_from_db()
        self.assertEqual(first.draft_payload['accounts'][0]['name'], '老板人民币')

        updated = save_day1_draft(
            payload=self.payload(name='新老板人民币', loose_sticks=3),
            expected_version=1,
            operator=self.partner,
        )
        self.assertEqual(updated.version, 2)
        updated.refresh_from_db()
        self.assertEqual(updated.draft_payload['accounts'][0]['name'], '新老板人民币')
        self.assertEqual(updated.draft_payload['inventory'][0]['loose_sticks'], 3)
        self.assertEqual(self.generated_counts(), (0, 0, 0, 0, 0))

    def test_saved_draft_serializes_original_amount_with_currency_precision(self):
        from accounting.day1_serializers import serialize_day1_state

        state = serialize_day1_state(self.save_draft())
        accounts = {row['slot']: row for row in state['draft']['accounts']}

        self.assertEqual(accounts['owner_cny']['original_amount'], '100.00')
        self.assertEqual(accounts['partner_cny']['original_amount'], '0.00')
        self.assertEqual(accounts['rub']['original_amount'], '1200.00')
        self.assertEqual(accounts['usdt']['original_amount'], '10.00000000')

    def test_incomplete_draft_saves_without_confirmation_validation(self):
        from accounting.day1 import Day1ValidationError, confirm_day1, save_day1_draft
        from accounting.day1_serializers import serialize_day1_state

        payload = self.payload()
        payload['accounts'][0]['name'] = ''
        payload['accounts'][0]['original_amount'] = ''
        payload['accounts'][0]['cny_book_cost'] = ''
        payload['inventory'][0]['box_quantity'] = 0
        payload['inventory'][0]['loose_sticks'] = 0
        payload['inventory'][0]['unit_cost_cny'] = ''

        draft = save_day1_draft(
            payload=payload, expected_version=0, operator=self.operator,
        )

        state = serialize_day1_state(draft)
        self.assertEqual(state['draft']['accounts'][0]['name'], '')
        self.assertEqual(state['draft']['accounts'][0]['original_amount'], '')
        self.assertEqual(state['draft']['inventory'][0]['unit_cost_cny'], '')
        with self.assertRaises(Day1ValidationError):
            confirm_day1(
                expected_version=draft.version,
                operator=self.operator,
                idempotency_key='incomplete-day1-draft',
            )
        self.assertEqual(self.generated_counts(), (0, 0, 0, 0, 0))

    def test_confirmation_posts_all_assets_through_day1_opening_shape(self):
        from accounting.day1 import confirm_day1, save_day1_draft

        draft = save_day1_draft(
            payload=self.payload(), expected_version=0, operator=self.operator,
        )

        result = confirm_day1(
            expected_version=draft.version,
            operator=self.operator,
            idempotency_key='day1-confirmation-shape',
        )

        self.assertEqual(result.business_date, date(2026, 8, 13))
        self.assertEqual(FundAccount.objects.count(), 4)
        ledger = LedgerTransaction.objects.get(source_type='day1_initialization')
        self.assertEqual(ledger.transaction_type, LedgerTransaction.TransactionType.DAY1_OPENING)
        self.assertEqual(ledger.postings.filter(account__isnull=False).count(), 3)
        self.assertEqual(ledger.postings.filter(category=LedgerPosting.Category.INVENTORY).count(), 1)
        self.assertEqual(ledger.postings.filter(category=LedgerPosting.Category.OPENING_CAPITAL).count(), 1)
        self.assertFalse(ledger.postings.filter(category=LedgerPosting.Category.OPENING_RETAINED_EARNINGS).exists())
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(result.opening_capital_cny, Decimal('607.50'))

        owner = FundAccount.objects.get(name='老板人民币')
        rub = FundAccount.objects.get(name='卢布账户')
        usdt = FundAccount.objects.get(name='USDT账户')
        self.assertEqual(account_snapshot(owner).original_balance, Decimal('100.00000000'))
        self.assertEqual(account_snapshot(rub).cny_book_cost, Decimal('100.00'))
        self.assertEqual(account_snapshot(usdt).original_balance, Decimal('10.00000000'))
        batch = PurchaseBatch.objects.get(source=PurchaseBatch.Source.OPENING)
        self.assertEqual((batch.original_box_quantity, batch.original_stick_quantity), (1, 2))
        self.assertEqual((batch.quantity, batch.original_cost_cny), (27, Decimal('337.50')))
        self.assertEqual(
            sum(ledger.postings.values_list('cny_amount', flat=True), Decimal('0.00')),
            Decimal('0.00'),
        )
        summary = result.completion_summary
        json.dumps(summary)
        self.assertEqual(len(summary['accounts']), 4)
        self.assertEqual(len(summary['inventory']), 1)
        self.assertEqual(summary['inventory'][0]['batch_id'], batch.pk)
        initialization = Day1Initialization.objects.get()
        self.assertEqual(initialization.status, Day1Initialization.Status.COMPLETED)
        self.assertEqual(initialization.completed_by, self.operator)
        self.assertIsNotNone(initialization.completed_at)

    def test_public_post_transaction_cannot_create_day1_opening(self):
        account = FundAccount.objects.create(
            name='旁路账户', currency='CNY',
            creation_idempotency_key='day1-public-bypass-account',
        )
        with self.assertRaisesRegex(LedgerError, 'Day 1'):
            post_transaction(
                transaction_type=LedgerTransaction.TransactionType.DAY1_OPENING,
                business_date=date(2026, 8, 13),
                postings=[
                    PostingInput(
                        account=account, currency='CNY',
                        amount=Decimal('1.00'), cny_amount=Decimal('1.00'),
                    ),
                    PostingInput(
                        category=LedgerPosting.Category.OPENING_CAPITAL,
                        currency='CNY', amount=Decimal('-1.00'),
                        cny_amount=Decimal('-1.00'),
                    ),
                ],
                operator=self.operator,
                idempotency_key='day1-public-bypass',
                source_type='day1_initialization', source_id='1',
            )

    def test_completed_confirmation_returns_frozen_result_for_every_replay(self):
        draft = self.save_draft()
        first = self.confirm(draft)
        counts = self.generated_counts()
        replay = self.confirm(draft)
        self.assertEqual(replay.completion_summary, first.completion_summary)
        self.assertEqual(self.generated_counts(), counts)
        different_key = self.confirm(draft, key='different-key')
        different_operator = self.confirm(draft, operator=self.partner)
        different_version = self.confirm(draft, version=draft.version + 1)
        self.assertEqual(different_key.completion_summary, first.completion_summary)
        self.assertEqual(different_operator.completion_summary, first.completion_summary)
        self.assertEqual(different_version.completion_summary, first.completion_summary)
        self.assertEqual(self.generated_counts(), counts)

    def test_confirmation_retries_the_whole_transaction_when_sqlite_is_locked(self):
        draft = self.save_draft()
        from accounting import day1
        original_gate = day1._acquire_sqlite_writer_gate
        attempts = 0

        def lock_twice():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise OperationalError('database is locked')
            return original_gate()

        with patch(
            'accounting.day1._acquire_sqlite_writer_gate',
            side_effect=lock_twice,
        ) as gate, patch('accounting.services.time.sleep'):
            result = self.confirm(draft)

        self.assertEqual(gate.call_count, 3)
        self.assertEqual(result.opening_capital_cny, Decimal('607.50'))
        self.assertEqual(self.generated_counts(), (4, 1, 5, 1, 1))

    def test_confirmation_rejects_box_size_not_declared_by_catalog(self):
        from accounting.day1 import Day1ValidationError

        self.cigar.packagings = json.dumps({
            'box_sizes': [10, 25],
        })
        self.cigar.save(update_fields=['packagings'])
        invalid = self.payload()
        invalid['inventory'][0]['box_size'] = 99

        draft = self.save_draft(invalid)
        with self.assertRaises(Day1ValidationError) as raised:
            self.confirm(draft)

        self.assertIn('inventory[0].box_size', raised.exception.details)
        self.assertEqual(self.generated_counts(), (0, 0, 0, 0, 0))

    def test_confirmation_revalidates_tampered_foreign_currency_draft(self):
        from accounting.day1 import Day1ValidationError

        draft = self.save_draft()
        draft.draft_payload['accounts'][2]['cny_book_cost'] = '0.00'
        draft.save(update_fields=['draft_payload'])

        with self.assertRaises(Day1ValidationError):
            self.confirm(draft)

        self.assertEqual(self.generated_counts(), (0, 0, 0, 0, 0))

    def test_confirmation_revalidates_tampered_zero_cost_inventory_draft(self):
        from accounting.day1 import Day1ValidationError

        draft = self.save_draft()
        draft.draft_payload['inventory'][0]['unit_cost_cny'] = '0.00'
        draft.save(update_fields=['draft_payload'])

        with self.assertRaises(Day1ValidationError):
            self.confirm(draft)

        self.assertEqual(self.generated_counts(), (0, 0, 0, 0, 0))

    def test_confirmation_revalidates_tampered_zero_quantity_inventory_draft(self):
        from accounting.day1 import Day1ValidationError

        draft = self.save_draft()
        draft.draft_payload['inventory'][0]['box_quantity'] = 0
        draft.draft_payload['inventory'][0]['loose_sticks'] = 0
        draft.save(update_fields=['draft_payload'])

        with self.assertRaises(Day1ValidationError):
            self.confirm(draft)

        self.assertEqual(self.generated_counts(), (0, 0, 0, 0, 0))

    def test_completed_initialization_rejects_draft_updates(self):
        from accounting.day1 import Day1Conflict, save_day1_draft

        draft = self.save_draft()
        self.confirm(draft)
        with self.assertRaises(Day1Conflict):
            save_day1_draft(
                payload=self.payload(), expected_version=draft.version,
                operator=self.partner,
            )

    def test_confirmation_rolls_back_every_generated_fact_on_inventory_failure(self):
        draft = self.save_draft()
        with patch(
            'cigars.inventory.StockMovement.objects.create',
            side_effect=RuntimeError('injected movement failure'),
        ):
            with self.assertRaises(RuntimeError):
                self.confirm(draft)
        self.assertEqual(self.generated_counts(), (0, 0, 0, 0, 0))
        draft.refresh_from_db()
        self.assertEqual(draft.status, Day1Initialization.Status.DRAFT)
        self.assertEqual(draft.version, 1)

    def test_confirmation_reports_existing_business_facts(self):
        from accounting.day1 import Day1Conflict

        draft = self.save_draft()
        FundAccount.objects.create(
            name='既有账户', currency='CNY',
            creation_idempotency_key='existing-before-day1',
        )
        with self.assertRaises(Day1Conflict) as raised:
            self.confirm(draft)
        self.assertIn('fund_accounts_exist', raised.exception.conflicts)
        draft.refresh_from_db()
        self.assertEqual(draft.status, Day1Initialization.Status.DRAFT)

    def assert_confirmation_conflict(self, draft, expected):
        from accounting.day1 import Day1Conflict

        with self.assertRaises(Day1Conflict) as raised:
            self.confirm(draft)
        self.assertIn(expected, raised.exception.conflicts)

    def existing_opening_batch(self):
        return create_purchase_batch(
            purchase_order_item=None, source=PurchaseBatch.Source.OPENING,
            cigar=self.cigar, quantity=1, remaining=1,
            physical_remaining=1, original_stick_quantity=1,
            physical_stick_quantity=1, available_stick_quantity=1,
            original_cost_cny=Decimal('1.00'),
            remaining_cost_cny=Decimal('1.00'),
            unit_cost_cny=Decimal('1.00'),
        )

    def test_confirmation_reports_existing_posted_ledger_fact(self):
        draft = self.save_draft()
        account = FundAccount.objects.create(
            name='既有流水账户', currency='CNY',
            creation_idempotency_key='existing-ledger-account',
        )
        from accounting.services import record_opening_balance
        record_opening_balance(
            account, '1.00', '1.00',
            LedgerPosting.Category.OPENING_CAPITAL, CUTOVER_DATE,
            self.operator, 'existing-ledger',
        )

        self.assert_confirmation_conflict(draft, 'posted_ledger_exists')

    def test_confirmation_reports_existing_purchase_batch_fact(self):
        draft = self.save_draft()
        self.existing_opening_batch()

        self.assert_confirmation_conflict(draft, 'purchase_batches_exist')

    def test_confirmation_reports_existing_stock_movement_fact(self):
        draft = self.save_draft()
        batch = self.existing_opening_batch()
        create_stock_movement(
            movement_type=StockMovement.MovementType.RECEIVE,
            cigar=self.cigar, purchase_batch=batch, quantity=1,
            operator=self.operator,
        )

        self.assert_confirmation_conflict(draft, 'stock_movements_exist')

    def test_invalid_draft_payload_is_saved_without_creating_business_facts(self):
        from accounting.day1 import Day1ValidationError, confirm_day1, save_day1_draft

        invalid = self.payload()
        invalid['accounts'][0]['cny_book_cost'] = '99.00'
        draft = save_day1_draft(
            payload=invalid, expected_version=0, operator=self.operator,
        )
        self.assertEqual(draft.draft_payload['accounts'], invalid['accounts'])
        self.assertEqual(draft.draft_payload['inventory'], invalid['inventory'])
        self.assertEqual(
            draft.draft_payload['business_date'], invalid['business_date'].isoformat(),
        )
        with self.assertRaises(Day1ValidationError):
            confirm_day1(
                expected_version=draft.version,
                operator=self.operator,
                idempotency_key='invalid-draft-confirm',
            )
        self.assertEqual(self.generated_counts(), (0, 0, 0, 0, 0))

    def test_confirmation_rejects_future_moscow_business_date(self):
        from accounting.day1 import Day1ValidationError

        invalid = self.payload()
        invalid['business_date'] = (
            moscow_business_date() + timedelta(days=1)
        ).isoformat()

        draft = self.save_draft(invalid)
        with self.assertRaises(Day1ValidationError) as raised:
            self.confirm(draft)

        self.assertIn('business_date', raised.exception.details)

    def test_opening_batches_work_in_search_and_privnote_inventory(self):
        from privnote.helpers import serialize_cigar_minimal
        from privnote.services.inventory import build_inventory_data

        draft = self.save_draft()
        self.confirm(draft)
        search = serialize_cigar_minimal(self.cigar, include_batches=True, stock_only=True)
        self.assertEqual(search['batches'][0]['box_size'], 25)
        inventory = build_inventory_data()
        self.assertEqual(inventory['total_items'], 1)
        self.assertEqual(inventory['brand_groups'][0]['items'][0]['box_size'], 25)


class Day1ConfirmationConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.operator = User.objects.create_user(
            'day1-concurrent-operator', password='pass', is_staff=True,
        )
        self.cigar = Cigar.objects.create(
            brand='Day 1 Concurrent Brand',
            english_name='Day 1 Concurrent Cigar',
            name='并发期初雪茄',
        )
        from accounting.day1 import save_day1_draft
        self.draft = save_day1_draft(
            payload={
                'business_date': date(2026, 8, 13),
                'accounts': [
                    {'slot': 'owner_cny', 'name': '并发我的人民币', 'currency': 'CNY', 'original_amount': '100.00', 'cny_book_cost': '100.00'},
                    {'slot': 'partner_cny', 'name': '并发合伙人人民币', 'currency': 'CNY', 'original_amount': '0.00', 'cny_book_cost': '0.00'},
                    {'slot': 'rub', 'name': '并发卢布账户', 'currency': 'RUB', 'original_amount': '1200.00', 'cny_book_cost': '100.00'},
                    {'slot': 'usdt', 'name': '并发 USDT', 'currency': 'USDT', 'original_amount': '10.00000000', 'cny_book_cost': '70.00'},
                ],
                'inventory': [
                    {'cigar_id': self.cigar.pk, 'box_size': 25, 'box_quantity': 1, 'loose_sticks': 2, 'unit_cost_cny': '12.50'},
                ],
            },
            expected_version=0,
            operator=self.operator,
        )

    def test_two_concurrent_confirmations_return_one_frozen_result(self):
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def submit(key):
            close_old_connections()
            try:
                operator = User.objects.get(pk=self.operator.pk)
                barrier.wait(timeout=10)
                from accounting.day1 import confirm_day1
                result = confirm_day1(
                    expected_version=self.draft.version,
                    operator=operator,
                    idempotency_key=key,
                )
                results.append(result)
            except Exception as error:
                errors.append(error)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=submit, args=('day1-concurrent-a',)),
            threading.Thread(target=submit, args=('day1-concurrent-b',)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].completion_summary, results[1].completion_summary)
        self.assertEqual(FundAccount.objects.count(), 4)
        self.assertEqual(
            LedgerTransaction.objects.filter(transaction_type='day1_opening').count(),
            1,
        )
        self.assertEqual(PurchaseBatch.objects.filter(source='opening').count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)


class Day1ModelTest(TestCase):
    def test_only_one_shared_company_initialization_can_exist(self):
        first = Day1Initialization.objects.create()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Day1Initialization.objects.create()

        self.assertEqual(first.singleton_key, 'company')
        self.assertEqual(Day1Initialization.objects.count(), 1)

    def test_opening_purchase_batch_does_not_require_historical_order_item(self):
        cigar = Cigar.objects.create(
            brand='Day 1 Brand',
            english_name='Day 1 Cigar',
            name='期初雪茄',
        )

        batch = create_purchase_batch(
            purchase_order_item=None,
            source=PurchaseBatch.Source.OPENING,
            cigar=cigar,
            quantity=10,
            remaining=10,
            physical_remaining=10,
            box_size=10,
            original_box_quantity=1,
            original_stick_quantity=0,
            physical_box_quantity=1,
            available_box_quantity=1,
            physical_stick_quantity=0,
            available_stick_quantity=0,
            original_cost_cny=Decimal('100.00'),
            remaining_cost_cny=Decimal('100.00'),
            unit_cost_cny=Decimal('10.00'),
        )

        self.assertIsNone(batch.purchase_order_item)
        self.assertEqual(batch.source, PurchaseBatch.Source.OPENING)

    def test_purchase_source_requires_purchase_order_item(self):
        cigar = Cigar.objects.create(
            brand='Day 1 Brand', english_name='Purchase Source Cigar', name='采购来源雪茄',
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            force_create_purchase_batch(
                purchase_order_item=None,
                source=PurchaseBatch.Source.PURCHASE,
                cigar=cigar,
                quantity=1,
                remaining=1,
                physical_remaining=1,
                original_cost_cny=Decimal('10.00'),
                remaining_cost_cny=Decimal('10.00'),
                unit_cost_cny=Decimal('10.00'),
            )

    def test_opening_source_rejects_purchase_order_item(self):
        user = User.objects.create_user('day1-source-user')
        supplier = Supplier.objects.create(name='Day 1 Source Supplier')
        cigar = Cigar.objects.create(
            brand='Day 1 Brand', english_name='Opening Source Cigar', name='期初来源雪茄',
        )
        order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=Decimal('1.00'), exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('10.00'), operator=user,
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=cigar, quantity=1, box_size=None,
            unit_price_rub=Decimal('1.00'), unit_price_cny=Decimal('10.00'),
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            force_create_purchase_batch(
                purchase_order_item=item,
                source=PurchaseBatch.Source.OPENING,
                cigar=cigar,
                quantity=1,
                remaining=1,
                physical_remaining=1,
                original_cost_cny=Decimal('10.00'),
                remaining_cost_cny=Decimal('10.00'),
                unit_cost_cny=Decimal('10.00'),
            )

    def test_opening_batch_is_safe_through_receive_endpoint_representation(self):
        operator = User.objects.create_user('day1-agent-user', password='pass', is_staff=True)
        cigar = Cigar.objects.create(
            brand='Day 1 Brand', english_name='Agent Opening Cigar', name='代理期初雪茄',
        )
        batch = create_purchase_batch(
            purchase_order_item=None,
            source=PurchaseBatch.Source.OPENING,
            cigar=cigar,
            quantity=1,
            remaining=1,
            physical_remaining=1,
            original_cost_cny=Decimal('10.00'),
            remaining_cost_cny=Decimal('10.00'),
            unit_cost_cny=Decimal('10.00'),
        )
        client = Client()
        client.force_login(operator)
        with patch('cigars.agent_api.receive_purchase_order', return_value=[batch]):
            response = client.post(
                '/api/agent/purchase-orders/receive/',
                data=json.dumps({
                    'operator_id': operator.pk,
                    'idempotency_key': 'day1-opening-receive',
                    'agent': {'agent_name': 'test'},
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['purchase_order'])
        self.assertEqual(response.json()['batch_source'], 'opening')


class Day1MigrationTest(TransactionTestCase):
    reset_sequences = True

    migrate_from = [
        ('accounting', '0010_day1_initialization'),
        ('cigars', '0033_guideconfiguration_userguideprogress'),
    ]
    migrate_to = [
        ('accounting', '0010_day1_initialization'),
        ('cigars', '0034_purchase_batch_source'),
    ]

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
        super().tearDown()

    def _make_legacy_batch(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = MigrationExecutor(connection).loader.project_state(self.migrate_from).apps
        UserModel = apps.get_model('cigars', 'User')
        CigarModel = apps.get_model('cigars', 'Cigar')
        SupplierModel = apps.get_model('cigars', 'Supplier')
        PurchaseOrderModel = apps.get_model('cigars', 'PurchaseOrder')
        PurchaseOrderItemModel = apps.get_model('cigars', 'PurchaseOrderItem')
        PurchaseBatchModel = apps.get_model('cigars', 'PurchaseBatch')
        operator = UserModel.objects.create(username='day1-migration-user', is_staff=True)
        cigar = CigarModel.objects.create(brand='Migration Brand', english_name='Migration Cigar', name='迁移雪茄')
        supplier = SupplierModel.objects.create(name='Day 1 Migration Supplier')
        order = PurchaseOrderModel.objects.create(
            supplier=supplier, rub_total=Decimal('1.00'), exchange_rate=Decimal('1.0000'),
            cny_total=Decimal('10.00'), operator=operator,
        )
        item = PurchaseOrderItemModel.objects.create(
            purchase_order=order, cigar=cigar, quantity=1, box_size=None,
            unit_price_rub=Decimal('1.00'), unit_price_cny=Decimal('10.00'),
        )
        return executor, PurchaseBatchModel.objects.create(
            purchase_order_item=item, cigar=cigar, quantity=1, remaining=1,
            physical_remaining=1, original_cost_cny=Decimal('10.00'),
            remaining_cost_cny=Decimal('10.00'), unit_cost_cny=Decimal('10.00'),
        )

    def test_legacy_batch_gets_purchase_source_on_0034(self):
        executor, batch = self._make_legacy_batch()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        migrated = executor.loader.project_state(self.migrate_to).apps.get_model('cigars', 'PurchaseBatch').objects.get(pk=batch.pk)
        self.assertEqual(migrated.source, 'purchase')
        self.assertIsNotNone(migrated.purchase_order_item_id)

    def test_rollback_refuses_opening_batches_with_clear_error(self):
        executor, batch = self._make_legacy_batch()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        PurchaseBatchModel = executor.loader.project_state(self.migrate_to).apps.get_model('cigars', 'PurchaseBatch')
        PurchaseBatchModel.objects.filter(pk=batch.pk).update(source='opening', purchase_order_item=None)

        migration = import_module('cigars.migrations.0034_purchase_batch_source')
        with connection.schema_editor() as schema_editor:
            with self.assertRaisesRegex(RuntimeError, 'opening batches'):
                migration.refuse_opening_batches_on_reverse(
                    executor.loader.project_state(self.migrate_to).apps,
                    schema_editor,
                )


class Day1DraftPayloadMigrationTest(TransactionTestCase):
    migrate_from = [('accounting', '0014_inventory_adjustment_transaction')]
    migrate_to = [('accounting', '0015_day1initialization_draft_payload')]

    def tearDown(self):
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes(),
        )
        super().tearDown()

    def assert_rollback_refused(self, draft_payload):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Initialization = apps.get_model('accounting', 'Day1Initialization')
        Initialization.objects.create(draft_payload=draft_payload)

        executor = MigrationExecutor(connection)
        with self.assertRaisesRegex(RuntimeError, '无法回滚'):
            executor.migrate(self.migrate_from)

    def test_legacy_relational_draft_is_copied_before_tables_are_removed(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        UserModel = old_apps.get_model('cigars', 'User')
        CigarModel = old_apps.get_model('cigars', 'Cigar')
        Initialization = old_apps.get_model('accounting', 'Day1Initialization')
        DraftAccount = old_apps.get_model('accounting', 'Day1DraftAccount')
        DraftInventory = old_apps.get_model('accounting', 'Day1DraftInventory')
        operator = UserModel.objects.create(username='draft-migration', is_staff=True)
        cigar = CigarModel.objects.create(
            brand='Migration Brand', english_name='Migration Draft', name='迁移草稿',
        )
        initialization = Initialization.objects.create(
            business_date=date(2026, 8, 13), updated_by_id=operator.pk,
        )
        DraftAccount.objects.create(
            initialization=initialization, slot='owner_cny',
            account_name='我的人民币', currency='CNY',
            original_amount=Decimal('100.00'), cny_book_cost=Decimal('100.00'),
        )
        DraftInventory.objects.create(
            initialization=initialization, cigar=cigar, box_size=25,
            box_quantity=1, loose_sticks=2, unit_cost_cny=Decimal('12.50'),
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        migrated = new_apps.get_model(
            'accounting', 'Day1Initialization',
        ).objects.get(pk=initialization.pk)

        self.assertEqual(migrated.draft_payload['business_date'], '2026-08-13')
        self.assertEqual(migrated.draft_payload['accounts'][0]['name'], '我的人民币')
        self.assertEqual(migrated.draft_payload['inventory'][0]['cigar_id'], cigar.pk)
        self.assertNotIn('accounting_day1draftaccount', connection.introspection.table_names())
        self.assertNotIn('accounting_day1draftinventory', connection.introspection.table_names())

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        restored_apps = executor.loader.project_state(self.migrate_from).apps
        restored_account = restored_apps.get_model(
            'accounting', 'Day1DraftAccount',
        ).objects.get(initialization_id=initialization.pk)
        restored_inventory = restored_apps.get_model(
            'accounting', 'Day1DraftInventory',
        ).objects.get(initialization_id=initialization.pk)
        self.assertEqual(restored_account.account_name, '我的人民币')
        self.assertEqual(restored_inventory.cigar_id, cigar.pk)

    def test_rollback_refuses_to_silently_drop_incomplete_json_draft(self):
        self.assert_rollback_refused({
            'business_date': '',
            'accounts': [{
                'slot': 'owner_cny', 'name': '', 'currency': 'CNY',
                'original_amount': '', 'cny_book_cost': '',
            }],
            'inventory': [],
        })

    def test_rollback_refuses_amount_precision_the_legacy_table_would_round(self):
        self.assert_rollback_refused({
            'business_date': None,
            'accounts': [{
                'slot': 'owner_cny', 'name': '老板人民币', 'currency': 'CNY',
                'original_amount': '1.00000000', 'cny_book_cost': '1.234',
            }],
            'inventory': [],
        })

    def test_rollback_refuses_amount_sqlite_cannot_store_losslessly(self):
        self.assert_rollback_refused({
            'business_date': None,
            'accounts': [{
                'slot': 'owner_cny', 'name': '老板人民币', 'currency': 'CNY',
                'original_amount': '123456789012.12345678',
                'cny_book_cost': '1.00',
            }],
            'inventory': [],
        })

    def test_rollback_refuses_fields_the_legacy_tables_cannot_store(self):
        self.assert_rollback_refused({
            'business_date': None,
            'accounts': [],
            'inventory': [],
            'future_field': '不能静默丢失',
        })
