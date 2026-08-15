from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from accounting.models import Day1Initialization, FundAccount, LedgerPosting, LedgerTransaction
from accounting.selectors import accounting_summary
from accounting.services import LedgerError, PostingInput, post_transaction, record_opening_balance
from cigars.models import Brand, Cigar, PurchaseBatch, PurchaseOrder, PurchaseOrderItem, SalesOrder, Supplier, User
from cigars.services import AgentContext, adjust_stock, create_sales_order, create_sales_order_draft, confirm_sales_order


class Task9BackendFixesTest(TestCase):
    business_date = date(2026, 8, 10)

    def setUp(self):
        self.operator = User.objects.create_user(username='task9-operator', password='pass', is_staff=True)
        self.brand = Brand.objects.create(english_name='Task9 Brand', name='Task9 品牌')
        self.cigar = Cigar.objects.create(brand=self.brand.english_name, english_name='Task9 Cigar', name='Task9 雪茄')

    def complete_day1(self):
        Day1Initialization.objects.create(singleton_key='company', status=Day1Initialization.Status.COMPLETED, business_date=self.business_date, completed_by=self.operator)

    def context(self, command, key):
        return AgentContext(agent_name='task9', agent_run_id='run', agent_request_id='request', command_name=command, idempotency_key=key)

    def account(self, name, currency, key):
        return FundAccount.objects.create(name=name, currency=currency, creation_idempotency_key=key, custodian=self.operator)

    def batch(self, quantity=3):
        supplier = Supplier.objects.create(name=f'Task9 supplier {PurchaseOrder.objects.count()}')
        order = PurchaseOrder.objects.create(supplier=supplier, rub_total=Decimal('1.00'), exchange_rate=Decimal('1.0000'), cny_total=Decimal('30.00'), operator=self.operator)
        item = PurchaseOrderItem.objects.create(purchase_order=order, cigar=self.cigar, quantity=quantity, box_size=25, unit_price_rub=Decimal('1.00'), unit_price_cny=Decimal('10.00'))
        return PurchaseBatch.objects.create(purchase_order_item=item, cigar=self.cigar, quantity=quantity, remaining=quantity, physical_remaining=quantity, original_cost_cny=Decimal(quantity * 10), remaining_cost_cny=Decimal(quantity * 10), unit_cost_cny=Decimal('10.00'))

    def test_in_transit_summary_uses_purchase_payment_business_date(self):
        self.complete_day1()
        account = self.account('Task9 RUB', FundAccount.Currency.RUB, 'task9-rub')
        record_opening_balance(account, '100', '100', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'task9-open-rub')
        supplier = Supplier.objects.create(name='Task9 transit supplier')
        order = PurchaseOrder.objects.create(supplier=supplier, rub_total=Decimal('10.00'), operator=self.operator)
        PurchaseOrderItem.objects.create(purchase_order=order, cigar=self.cigar, quantity=25, box_size=25, box_quantity=1, unit_price_rub_per_box=Decimal('10.00'), packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE)
        from accounting.purchase_actions import pay_purchase_order
        payment = pay_purchase_order(purchase_order_id=order.id, rub_account_id=account.id, business_date=self.business_date, operator=self.operator, idempotency_key='task9-payment-date')
        self.assertEqual(payment.business_date, self.business_date)
        self.assertEqual(accounting_summary(as_of=self.business_date, require_current=False)['purchase_in_transit_cny'], Decimal('10.00'))

    def test_generic_ledger_replay_rejects_changed_postings(self):
        self.complete_day1()
        account = self.account('Task9 CNY', FundAccount.Currency.CNY, 'task9-cny')
        kwargs = dict(transaction_type=LedgerTransaction.TransactionType.TRANSFER, business_date=self.business_date, operator=self.operator, idempotency_key='task9-generic-replay', description='原说明', source_type='task9', source_id='1')
        post_transaction(postings=[PostingInput(account=account, currency='CNY', amount=Decimal('1'), cny_amount=Decimal('1')), PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-1'), cny_amount=Decimal('-1'))], **kwargs)
        with self.assertRaisesRegex(LedgerError, 'idempotency_conflict'):
            post_transaction(postings=[PostingInput(account=account, currency='CNY', amount=Decimal('2'), cny_amount=Decimal('2')), PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-2'), cny_amount=Decimal('-2'))], **kwargs)

    def test_generic_ledger_replay_survives_operator_and_account_state_changes(self):
        self.complete_day1()
        account = self.account('Task9 replay CNY', FundAccount.Currency.CNY, 'task9-replay-state')
        kwargs = dict(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            business_date=self.business_date, operator=self.operator,
            idempotency_key='task9-replay-state', description='状态重放',
            source_type='task9', source_id='state',
        )
        first = post_transaction(
            postings=[
                PostingInput(account=account, currency='CNY', amount=Decimal('1'), cny_amount=Decimal('1')),
                PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-1'), cny_amount=Decimal('-1')),
            ], **kwargs,
        )
        User.objects.filter(pk=self.operator.pk).update(is_staff=False)
        FundAccount.objects.filter(pk=account.pk).update(is_active=False)

        replay = post_transaction(
            postings=[
                PostingInput(account=account, currency='CNY', amount=Decimal('1'), cny_amount=Decimal('1')),
                PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-1'), cny_amount=Decimal('-1')),
            ], **kwargs,
        )

        self.assertEqual(replay.pk, first.pk)

    def test_opening_replay_survives_operator_and_account_state_changes(self):
        self.complete_day1()
        account = self.account('Task9 opening replay state', FundAccount.Currency.CNY, 'task9-opening-state')
        first = record_opening_balance(
            account, '10.00', '10.00', LedgerPosting.Category.OPENING_CAPITAL,
            self.business_date, self.operator, 'task9-opening-state',
        )
        User.objects.filter(pk=self.operator.pk).update(is_staff=False)
        FundAccount.objects.filter(pk=account.pk).update(is_active=False)

        replay = record_opening_balance(
            account, '10.00', '10.00', LedgerPosting.Category.OPENING_CAPITAL,
            self.business_date, self.operator, 'task9-opening-state',
        )

        self.assertEqual(replay.pk, first.pk)

    def test_generic_ledger_replay_normalizes_metadata_strings(self):
        self.complete_day1()
        account = self.account('Task9 metadata CNY', FundAccount.Currency.CNY, 'task9-metadata')
        kwargs = dict(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            business_date=self.business_date, operator=self.operator,
            idempotency_key='task9-metadata', description=None,
            source_type=123, source_id=None,
        )
        first = post_transaction(
            postings=[
                PostingInput(account=account, currency='CNY', amount=Decimal('1'), cny_amount=Decimal('1')),
                PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-1'), cny_amount=Decimal('-1')),
            ], **kwargs,
        )

        replay = post_transaction(
            postings=[
                PostingInput(account=account, currency='CNY', amount=Decimal('1'), cny_amount=Decimal('1')),
                PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-1'), cny_amount=Decimal('-1')),
            ], **kwargs,
        )

        self.assertEqual(replay.pk, first.pk)

    def test_opening_replay_rejects_changed_account(self):
        self.complete_day1()
        a = self.account('Task9 opening A', 'CNY', 'task9-open-a')
        b = self.account('Task9 opening B', 'CNY', 'task9-open-b')
        record_opening_balance(a, '10', '10', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'task9-opening-replay')
        with self.assertRaisesRegex(LedgerError, 'idempotency_conflict'):
            record_opening_balance(b, '10', '10', LedgerPosting.Category.OPENING_CAPITAL, self.business_date, self.operator, 'task9-opening-replay')

    def test_stock_adjustment_requires_nonblank_reason_before_mutation(self):
        self.complete_day1()
        batch = self.batch(quantity=2)
        with self.assertRaisesRegex(Exception, '原因不能为空'):
            adjust_stock(
                cigar_id=self.cigar.id, quantity_delta=-1, operator=self.operator,
                batch_id=batch.id, reason='   ', business_date=self.business_date,
                agent_context=self.context('adjust_stock', 'task9-adjust-empty-reason'),
            )
        self.assertEqual(LedgerTransaction.objects.count(), 0)
        from cigars.models import StockMovement
        self.assertEqual(StockMovement.objects.count(), 0)
        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 2)

    def test_formal_sales_and_adjustment_are_blocked_before_day1(self):
        batch = self.batch()
        with self.assertRaisesRegex(Exception, 'day1_incomplete'):
            create_sales_order(items=[{'cigar_id': self.cigar.id, 'quantity': 1, 'unit_price': '20.00'}], operator=self.operator, agent_context=self.context('create_sales_order', 'task9-sales-before-day1'))
        with self.assertRaisesRegex(Exception, 'day1_incomplete'):
            adjust_stock(cigar_id=self.cigar.id, quantity_delta=-1, operator=self.operator, batch_id=batch.id, reason='盘亏', business_date=self.business_date, agent_context=self.context('adjust_stock', 'task9-adjust-before-day1'))

    def test_stock_adjustment_posts_loss_and_replay_is_side_effect_free(self):
        self.complete_day1()
        batch = self.batch(quantity=3)
        ctx = self.context('adjust_stock', 'task9-adjust-replay')
        adjust_stock(cigar_id=self.cigar.id, quantity_delta=-1, operator=self.operator,
                     batch_id=batch.id, reason='盘亏', business_date=self.business_date,
                     agent_context=ctx)
        replay = adjust_stock(cigar_id=self.cigar.id, quantity_delta=-1, operator=self.operator,
                              batch_id=batch.id, reason='盘亏', business_date=self.business_date,
                              agent_context=ctx)
        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 2)
        tx = LedgerTransaction.objects.get(idempotency_key=ctx.idempotency_key)
        self.assertEqual(tx.transaction_type, LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT)
        self.assertEqual(tx.postings.filter(category=LedgerPosting.Category.INVENTORY_ADJUSTMENT_LOSS).count(), 1)
        self.assertEqual(replay.pk, batch.pk)

    def test_stock_adjustment_replay_rejects_changed_cost_or_type(self):
        self.complete_day1()
        batch = self.batch(quantity=1)
        key = 'task9-adjust-parameter-conflict'
        adjust_stock(cigar_id=self.cigar.id, quantity_delta=1, operator=self.operator,
                     batch_id=batch.id, unit_cost_cny='10.00', adjustment_type='LOSS',
                     reason='盘盈', business_date=self.business_date,
                     agent_context=self.context('adjust_stock', key))
        with self.assertRaisesRegex(Exception, 'idempotency_conflict'):
            adjust_stock(cigar_id=self.cigar.id, quantity_delta=1, operator=self.operator,
                         batch_id=batch.id, unit_cost_cny='20.00', adjustment_type='DAMAGE',
                         reason='盘盈', business_date=self.business_date,
                         agent_context=self.context('adjust_stock', key))

    def test_stock_adjustment_source_fingerprint_is_stable_and_bounded(self):
        self.complete_day1()
        batch = self.batch(quantity=1)
        adjust_stock(
            cigar_id=self.cigar.id, quantity_delta=1, operator=self.operator,
            batch_id=batch.id, unit_cost_cny='10', adjustment_type='LOSS',
            reason='盘盈', business_date=self.business_date,
            agent_context=self.context('adjust_stock', 'task9-adjust-fingerprint-a'),
        )
        adjust_stock(
            cigar_id=self.cigar.id, quantity_delta=1, operator=self.operator,
            batch_id=batch.id, unit_cost_cny='10.00', adjustment_type='LOSS',
            reason='盘盈', business_date=self.business_date,
            agent_context=self.context('adjust_stock', 'task9-adjust-fingerprint-b'),
        )
        source_ids = list(LedgerTransaction.objects.filter(
            transaction_type=LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
        ).values_list('source_id', flat=True))
        self.assertEqual(len(source_ids), 2)
        self.assertEqual(source_ids[0], source_ids[1])
        self.assertTrue(source_ids[0].startswith('stock_adjustment:'))
        self.assertEqual(len(source_ids[0]), len('stock_adjustment:') + 64 + 1 + len(str(batch.id)))
        self.assertTrue(source_ids[0].endswith(f':{batch.id}'))

    def test_stock_adjustment_replay_without_batch_id_returns_original_result_batch(self):
        self.complete_day1()
        first = self.batch(quantity=1)
        second = self.batch(quantity=1)
        # 让 FIFO 顺序与主键顺序相反，暴露按最新主键猜结果的错误。
        PurchaseBatch.objects.filter(pk=first.pk).update(
            purchased_at=first.purchased_at + timedelta(days=1),
        )
        context = self.context('adjust_stock', 'task9-adjust-result-batch')
        result = adjust_stock(
            cigar_id=self.cigar.id, quantity_delta=-2, operator=self.operator,
            reason='跨批次盘亏', business_date=self.business_date,
            agent_context=context,
        )
        replay = adjust_stock(
            cigar_id=self.cigar.id, quantity_delta=-2, operator=self.operator,
            reason='跨批次盘亏', business_date=self.business_date,
            agent_context=context,
        )
        self.assertEqual(result.pk, first.pk)
        self.assertEqual(replay.pk, result.pk)
        self.assertEqual(LedgerTransaction.objects.filter(idempotency_key=context.idempotency_key).count(), 1)
        second.refresh_from_db()
        self.assertEqual(second.remaining, 0)

    def test_positive_stock_adjustment_posts_inventory_gain(self):
        self.complete_day1()
        batch = self.batch(quantity=1)
        adjust_stock(cigar_id=self.cigar.id, quantity_delta=1, operator=self.operator,
                     batch_id=batch.id, unit_cost_cny='10.00', reason='盘盈',
                     business_date=self.business_date,
                     agent_context=self.context('adjust_stock', 'task9-adjust-gain'))
        tx = LedgerTransaction.objects.get(idempotency_key='task9-adjust-gain')
        self.assertEqual(tx.postings.get(category=LedgerPosting.Category.INVENTORY_ADJUSTMENT_GAIN).cny_amount, Decimal('-10.00'))

    def test_confirm_and_cancel_sales_gates_are_enforced_at_service_boundary(self):
        batch = self.batch(quantity=1)
        draft = create_sales_order_draft(
            items=[{'cigar_id': self.cigar.id, 'quantity': 1, 'unit_price': '20.00'}],
            operator=self.operator,
            agent_context=self.context('create_sales_order_draft', 'task9-gate-draft'),
        )
        with self.assertRaisesRegex(Exception, 'day1_incomplete'):
            confirm_sales_order(
                sales_order_id=draft.id, operator=self.operator,
                agent_context=self.context('confirm_sales_order', 'task9-gate-confirm'),
            )
        self.complete_day1()
        confirmed = confirm_sales_order(
            sales_order_id=draft.id, operator=self.operator,
            agent_context=self.context('confirm_sales_order', 'task9-gate-confirm-ok'),
        )
        Day1Initialization.objects.filter(singleton_key='company').update(
            status=Day1Initialization.Status.DRAFT,
        )
        with self.assertRaisesRegex(Exception, 'day1_incomplete'):
            from cigars.services import cancel_confirmed_sales_order
            cancel_confirmed_sales_order(
                sales_order_id=confirmed.id, operator=self.operator,
                agent_context=self.context('cancel_confirmed_sales_order', 'task9-gate-cancel'),
            )
        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 0)

    def test_confirm_sales_order_preserves_customer_transport_fee(self):
        self.complete_day1()
        self.batch(quantity=1)
        order = create_sales_order_draft(items=[{'cigar_id': self.cigar.id, 'quantity': 1, 'unit_price': '20.00'}], operator=self.operator, customer_transport_fee_cny='30.00', transport_payer='customer', agent_context=self.context('create_sales_order_draft', 'task9-draft-transport'))
        confirmed = confirm_sales_order(sales_order_id=order.id, operator=self.operator, agent_context=self.context('confirm_sales_order', 'task9-confirm-transport'))
        self.assertEqual(confirmed.customer_transport_fee_cny, Decimal('30.00'))
        self.assertEqual(confirmed.transport_payer, SalesOrder.TransportPayer.CUSTOMER)
        self.assertEqual(confirmed.amount_due_cny, Decimal('50.00'))
