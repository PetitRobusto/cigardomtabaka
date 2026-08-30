import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import OperationalError, connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounting.action_serializers import serialize_purchase_order
from accounting.models import (
    Day1Initialization, Dividend, Expense, FundAccount, LedgerPosting, LedgerTransaction,
)
from accounting.services import record_opening_balance
from accounting.mutation_scope import ledger_mutation_scope
from cigars.models import Brand, Cigar, PurchaseBatch, PurchaseOrder, PurchaseOrderItem, Supplier, User


class ActionApiContractTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.operator = User.objects.create_user(
            'task7-action-api', password='pass', is_staff=True,
        )
        self.client.force_login(self.operator)

    def complete_day1(self):
        Day1Initialization.objects.create(
            singleton_key='company', status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10), completed_by=self.operator,
        )

    def purchase_payload(self, price='100.00'):
        brand = Brand.objects.create(english_name=f'Action Brand {Supplier.objects.count()}', name='动作品牌')
        cigar = Cigar.objects.create(brand=brand.english_name, english_name=f'Action Cigar {Supplier.objects.count()}', name='动作雪茄')
        supplier = Supplier.objects.create(name=f'Action Supplier {Supplier.objects.count()}')
        return supplier, cigar, {
            'supplier_id': supplier.pk,
            'business_date': '2026-08-14',
            'items': [{'cigar_id': cigar.pk, 'box_size': 25, 'box_quantity': 1, 'unit_price_rub_per_box': price}],
        }

    def draft_purchase(self, status=PurchaseOrder.Status.DRAFT):
        supplier, cigar, _ = self.purchase_payload()
        order = PurchaseOrder.objects.create(
            supplier=supplier, rub_total=Decimal('100.00'), operator=self.operator,
            status=PurchaseOrder.Status.DRAFT, draft_business_date=date(2026, 8, 14),
        )
        PurchaseOrderItem.objects.create(
            purchase_order=order, cigar=cigar, quantity=25, box_size=25,
            box_quantity=1, unit_price_rub_per_box=Decimal('100.00'),
            packaging_status=PurchaseOrderItem.PackagingStatus.NORMALIZED,
        )
        if status != PurchaseOrder.Status.DRAFT:
            order.status = status
            order.paid_cny_cost = Decimal('100.00')
            order.paid_at = timezone.now()
            order.payment_idempotency_key = f'test-payment-{order.pk}'
            with ledger_mutation_scope(
                reason='purchase_payment', model='cigars.PurchaseOrder', operator=self.operator,
                allowed_fields={'status', 'paid_cny_cost', 'paid_at', 'payment_idempotency_key'},
            ):
                order.save(update_fields=['status', 'paid_cny_cost', 'paid_at', 'payment_idempotency_key'])
        return order

    def request(self, method, path, body=None, key='task7-api-key', **headers):
        return getattr(self.client, method)(
            path, data=json.dumps(body or {}), content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key, **headers,
        )

    def test_action_endpoints_enforce_method_contracts(self):
        self.assertEqual(self.client.post('/api/accounting/actions/').status_code, 405)
        self.assertEqual(self.client.get('/api/accounting/purchases/1/pay/').status_code, 405)
        self.assertEqual(self.client.delete('/api/accounting/purchases/1/').status_code, 405)
        self.assertEqual(self.client.patch('/api/accounting/dividends/').status_code, 405)
        self.assertEqual(self.client.get('/api/accounting/dividends/1/preview/').status_code, 405)
        self.assertEqual(self.client.get('/api/accounting/dividends/1/confirm/').status_code, 405)

    def test_invalid_action_input_is_bad_request_and_day1_is_conflict(self):
        invalid = self.request('post', '/api/accounting/expenses/', {'category': 'salary'}, key='task7-invalid')
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()['code'], 'input_error')

        day1 = self.request('post', '/api/accounting/expenses/', {
            'category': 'salary', 'amount': '1.00', 'fund_account_id': 1,
            'business_date': '2026-08-14',
        }, key='task7-day1')
        self.assertEqual(day1.status_code, 409)
        self.assertEqual(day1.json()['code'], 'day1_incomplete')

    def test_incomplete_purchase_is_saved_as_draft_without_business_validation(self):
        self.complete_day1()
        _, _, payload = self.purchase_payload()
        payload['items'][0]['box_quantity'] = 0

        response = self.request(
            'post', '/api/accounting/purchases/', payload,
            key='task7-invalid-packaging',
        )

        self.assertEqual(response.status_code, 201)
        purchase = response.json()['purchase_order']
        self.assertFalse(purchase['draft_complete'])
        self.assertEqual(purchase['items'][0]['packaging_status'], 'review_required')

    def test_if_match_mismatch_is_version_conflict(self):
        response = self.request(
            'patch', '/api/accounting/purchases/1/', {'expected_version': 1, 'items': []},
            key='task7-version', HTTP_IF_MATCH='2',
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'version_conflict')

    def test_all_formal_action_writes_are_blocked_before_day1(self):
        supplier, cigar, payload = self.purchase_payload()
        create = self.request('post', '/api/accounting/purchases/', payload, key='guard-create')
        self.assertEqual(create.status_code, 409)
        self.assertEqual(create.json()['code'], 'day1_incomplete')
        draft = self.draft_purchase()
        for path, body, method, key in (
            (f'/api/accounting/purchases/{draft.pk}/', {'expected_version': draft.version, 'items': payload['items']}, 'patch', 'guard-update'),
            (f'/api/accounting/purchases/{draft.pk}/pay/', {'business_date': '2026-08-14', 'rub_account_id': 1}, 'post', 'guard-pay'),
            (f'/api/accounting/purchases/{draft.pk}/receive/', {'business_date': '2026-08-14'}, 'post', 'guard-receive'),
            (f'/api/accounting/purchases/{draft.pk}/reverse-receive/', {'business_date': '2026-08-14', 'note': '撤回测试'}, 'post', 'guard-reverse-receive'),
            (f'/api/accounting/purchases/{draft.pk}/cancel/', {'expected_version': draft.version}, 'post', 'guard-cancel'),
        ):
            response = self.request(method, path, body, key=key)
            self.assertEqual(response.status_code, 409, path)
            self.assertEqual(response.json()['code'], 'day1_incomplete', path)
        expense = self.request('post', '/api/accounting/expenses/', {
            'category': 'salary', 'amount': '1.00', 'fund_account_id': 1, 'business_date': '2026-08-14',
        }, key='guard-expense')
        self.assertEqual(expense.json()['code'], 'day1_incomplete')
        dividend = self.request('post', '/api/accounting/dividends/', {
            'total_cny': '1.00', 'business_date': '2026-08-14',
        }, key='guard-dividend')
        self.assertEqual(dividend.status_code, 409)
        self.assertEqual(dividend.json()['code'], 'day1_incomplete')
        draft_dividend = Dividend.objects.create(
            total_cny=Decimal('1.00'), partner_a_amount_cny=Decimal('0.50'),
            partner_b_amount_cny=Decimal('0.50'), business_date=date(2026, 8, 14),
            created_by=self.operator, updated_by=self.operator,
        )
        for path, body, method, key in (
            (f'/api/accounting/dividends/{draft_dividend.pk}/', {
                'total_cny': '1.00', 'partner_a_amount_cny': '0.50', 'partner_b_amount_cny': '0.50',
                'partner_a_account_id': 1, 'partner_b_account_id': 2, 'expected_version': 1,
            }, 'patch', 'guard-dividend-update'),
            (f'/api/accounting/dividends/{draft_dividend.pk}/preview/', {}, 'post', 'guard-dividend-preview'),
            (f'/api/accounting/dividends/{draft_dividend.pk}/confirm/', {
                'expected_version': 1, 'warning_fingerprint': 'not-current', 'warning_ack': False,
            }, 'post', 'guard-dividend-confirm'),
        ):
            response = self.request(method, path, body, key=key)
            self.assertEqual(response.status_code, 409, path)
            self.assertEqual(response.json()['code'], 'day1_incomplete', path)

    def test_dividend_preview_requires_idempotency_key(self):
        self.complete_day1()
        draft = Dividend.objects.create(
            total_cny=Decimal('1.00'), partner_a_amount_cny=Decimal('0.50'),
            partner_b_amount_cny=Decimal('0.50'), business_date=date(2026, 8, 14),
            created_by=self.operator, updated_by=self.operator,
        )
        response = self.client.post(
            f'/api/accounting/dividends/{draft.pk}/preview/',
            data=json.dumps({}), content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'input_error')

    def test_purchase_key_conflict_pending_states_and_decimal_serialization(self):
        self.complete_day1()
        supplier, cigar, payload = self.purchase_payload()
        first = self.request('post', '/api/accounting/purchases/', payload, key='purchase-api-replay')
        conflict_payload = {**payload, 'items': [{**payload['items'][0], 'unit_price_rub_per_box': '101.00'}]}
        conflict = self.request('post', '/api/accounting/purchases/', conflict_payload, key='purchase-api-replay')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['code'], 'idempotency_conflict')
        self.assertIsInstance(first.json()['purchase_order']['rub_total'], str)
        self.draft_purchase(PurchaseOrder.Status.IN_TRANSIT)
        pending = self.client.get('/api/accounting/actions/')
        self.assertEqual(pending.status_code, 200)
        self.assertEqual({row['status'] for row in pending.json()['purchases']}, {'draft', 'in_transit'})

    def test_purchase_http_pay_replay_and_receive_replay(self):
        self.complete_day1()
        rub = FundAccount.objects.create(name='采购付款卢布', currency='RUB', creation_idempotency_key='purchase-flow-rub')
        record_opening_balance(
            rub, Decimal('1000.00'), Decimal('100.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'purchase-flow-opening',
        )
        _, _, payload = self.purchase_payload()
        created = self.request('post', '/api/accounting/purchases/', payload, key='purchase-flow-create')
        order_id = created.json()['purchase_order']['id']
        pay_body = {'rub_account_id': rub.pk, 'business_date': '2026-08-14'}
        paid = self.request('post', f'/api/accounting/purchases/{order_id}/pay/', pay_body, key='purchase-flow-pay')
        replayed = self.request('post', f'/api/accounting/purchases/{order_id}/pay/', pay_body, key='purchase-flow-pay')
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(paid.json()['purchase_order']['id'], order_id)
        self.assertEqual(paid.json()['purchase_order']['status'], PurchaseOrder.Status.IN_TRANSIT)
        self.assertIsInstance(paid.json()['purchase_order']['paid_cny_cost'], str)
        receive_body = {'business_date': '2026-08-14'}
        received = self.request(
            'post', f'/api/accounting/purchases/{order_id}/receive/', receive_body,
            key='purchase-flow-receive',
        )
        received_replay = self.request(
            'post', f'/api/accounting/purchases/{order_id}/receive/', receive_body,
            key='purchase-flow-receive',
        )
        self.assertEqual(received.status_code, 200)
        self.assertEqual(received_replay.json(), received.json())
        order = PurchaseOrder.objects.get(pk=order_id)
        self.assertEqual(order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(PurchaseBatch.objects.filter(purchase_order_item__purchase_order_id=order_id).count(), 1)
        self.assertEqual(len(received.json()['purchase_batches']), 1)

    def test_salary_from_rub_is_supported_and_operational_error_is_busy(self):
        self.complete_day1()
        rub = FundAccount.objects.create(name='动作卢布', currency='RUB', creation_idempotency_key='action-rub')
        record_opening_balance(rub, Decimal('10.00'), Decimal('1.00'), LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10), self.operator, 'action-rub-opening')
        response = self.request('post', '/api/accounting/expenses/', {
            'category': 'salary', 'amount': '1.00', 'fund_account_id': rub.pk, 'business_date': '2026-08-14',
        }, key='action-rub-salary')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['expense'])
        with patch('accounting.views.record_expense', side_effect=OperationalError('database is locked')):
            expense_count = Expense.objects.count()
            ledger_count = LedgerTransaction.objects.count()
            busy = self.request('post', '/api/accounting/expenses/', {
                'category': 'salary', 'amount': '1.00', 'fund_account_id': rub.pk, 'business_date': '2026-08-14',
            }, key='action-busy')
        self.assertEqual(busy.status_code, 503)
        self.assertEqual(busy.json()['code'], 'busy')
        self.assertEqual(Expense.objects.count(), expense_count)
        self.assertEqual(LedgerTransaction.objects.count(), ledger_count)

    def test_expense_subcategory_round_trips_through_api(self):
        self.complete_day1()
        cny = FundAccount.objects.create(name='明细人民币账户', currency='CNY', creation_idempotency_key='action-subcategory-cny')
        record_opening_balance(cny, Decimal('100.00'), Decimal('100.00'), LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10), self.operator, 'action-subcategory-opening')
        response = self.request('post', '/api/accounting/expenses/', {
            'category': 'other', 'subcategory': 'transport_taxi', 'amount': '25.00',
            'fund_account_id': cny.pk, 'business_date': '2026-08-14',
        }, key='action-subcategory-taxi')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['expense']['subcategory'], 'transport_taxi')

        listing = self.client.get('/api/accounting/expenses/?month=2026-08')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()['expenses'][0]['category_label'], '交通 / 物流')
        self.assertEqual(listing.json()['expenses'][0]['subcategory_label'], '交通 / 物流 · 打车')
        self.assertEqual(listing.json()['expenses'][0]['fund_account_name'], '明细人民币账户')
        invalid_month = self.client.get('/api/accounting/expenses/?month=2026-8')
        self.assertEqual(invalid_month.status_code, 400)

    def test_expense_reversal_http_flow_and_replay(self):
        self.complete_day1()
        cny = FundAccount.objects.create(
            name='费用冲正人民币', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='action-expense-reversal-cny',
        )
        record_opening_balance(
            cny, Decimal('100.00'), Decimal('100.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'action-expense-reversal-opening',
        )
        created = self.request('post', '/api/accounting/expenses/', {
            'category': 'salary', 'amount': '10.00',
            'fund_account_id': cny.pk, 'business_date': '2026-08-14',
        }, key='action-expense-reversal-original')
        self.assertEqual(created.status_code, 201)
        expense_id = created.json()['expense']['id']
        body = {'business_date': '2026-08-15', 'note': '重复录入'}
        reversed_response = self.request(
            'post', f'/api/accounting/expenses/{expense_id}/reverse/',
            body, key='action-expense-reversal',
        )
        replayed = self.request(
            'post', f'/api/accounting/expenses/{expense_id}/reverse/',
            body, key='action-expense-reversal',
        )
        self.assertEqual(reversed_response.status_code, 200)
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(replayed.json(), reversed_response.json())
        payload = reversed_response.json()['expense']
        self.assertTrue(payload['reversed'])
        self.assertIsNotNone(payload['reversal_transaction_id'])
        self.assertEqual(payload['reversal_business_date'], '2026-08-15')

    def test_expense_reversal_http_errors_are_stable(self):
        self.complete_day1()
        cny = FundAccount.objects.create(
            name='费用冲正错误人民币', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='action-expense-reversal-error-cny',
        )
        record_opening_balance(
            cny, Decimal('100.00'), Decimal('100.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'action-expense-reversal-error-opening',
        )
        created = self.request('post', '/api/accounting/expenses/', {
            'category': 'salary', 'amount': '10.00',
            'fund_account_id': cny.pk, 'business_date': '2026-08-14',
        }, key='action-expense-reversal-error-original')
        expense_id = created.json()['expense']['id']
        missing_reason = self.request(
            'post', f'/api/accounting/expenses/{expense_id}/reverse/',
            {'business_date': '2026-08-15'}, key='action-expense-reversal-missing-reason',
        )
        self.assertEqual(missing_reason.status_code, 400)
        self.assertEqual(missing_reason.json()['code'], 'reason_required')
        reversed_response = self.request(
            'post', f'/api/accounting/expenses/{expense_id}/reverse/',
            {'business_date': '2026-08-15', 'note': '录入错误'},
            key='action-expense-reversal-error-action',
        )
        self.assertEqual(reversed_response.status_code, 200)
        duplicate = self.request(
            'post', f'/api/accounting/expenses/{expense_id}/reverse/',
            {'business_date': '2026-08-15', 'note': '再次撤回'},
            key='action-expense-reversal-error-action-2',
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()['code'], 'already_reversed')
        missing = self.request(
            'post', '/api/accounting/expenses/999999/reverse/',
            {'business_date': '2026-08-15', 'note': '不存在'},
            key='action-expense-reversal-missing',
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()['code'], 'expense_not_found')

    def exchange_payload(self):
        self.complete_day1()
        cny = FundAccount.objects.create(
            name='换汇人民币', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='exchange-contract-cny',
        )
        rub = FundAccount.objects.create(
            name='换汇卢布', currency=FundAccount.Currency.RUB,
            creation_idempotency_key='exchange-contract-rub',
        )
        return {
            'source_account_id': cny.pk,
            'rub_account_id': rub.pk,
            'source_amount': '1.00',
            'rub_amount': '12.00',
            'business_date': '2026-08-14',
        }

    def test_exchange_missing_account_is_not_found(self):
        base = self.exchange_payload()
        missing = self.request(
            'post', '/api/accounting/exchanges/',
            {**base, 'source_account_id': 999999},
            key='exchange-contract-missing',
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()['code'], 'account_not_found')

    def test_exchange_excess_precision_is_bad_request(self):
        base = self.exchange_payload()
        precision = self.request(
            'post', '/api/accounting/exchanges/',
            {**base, 'source_amount': '1.001'},
            key='exchange-contract-precision',
        )
        self.assertEqual(precision.status_code, 400)
        self.assertEqual(precision.json()['code'], 'invalid_money_precision')

    def test_exchange_operational_error_is_busy(self):
        base = self.exchange_payload()
        with patch(
            'accounting.views._exchange_to_rub_with_result',
            side_effect=OperationalError('database is locked'),
        ):
            self.client.raise_request_exception = False
            try:
                busy = self.request(
                    'post', '/api/accounting/exchanges/', base,
                    key='exchange-contract-busy',
                )
            finally:
                self.client.raise_request_exception = True
        self.assertEqual(busy.status_code, 503)
        self.assertEqual(busy.json()['code'], 'busy')

    def test_purchase_serializer_reuses_prefetched_items(self):
        for _ in range(3):
            self.draft_purchase()
        orders = list(
            PurchaseOrder.objects.order_by('id').select_related('supplier').prefetch_related('items__cigar')
        )

        with CaptureQueriesContext(connection) as captured:
            payload = [serialize_purchase_order(order) for order in orders]

        self.assertEqual(len(payload), 3)
        self.assertEqual(len(captured), 0)

    def test_action_notes_must_be_strings(self):
        self.complete_day1()
        cny = FundAccount.objects.create(
            name='note 校验人民币', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='note-validation-cny',
        )
        record_opening_balance(
            cny, Decimal('10.00'), Decimal('10.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'note-validation-opening',
        )
        _, _, purchase = self.purchase_payload()
        requests = (
            (
                '/api/accounting/purchases/',
                {**purchase, 'note': {'invalid': True}},
                'note-validation-purchase',
            ),
            (
                '/api/accounting/expenses/',
                {
                    'category': 'salary', 'amount': '1.00',
                    'fund_account_id': cny.pk,
                    'business_date': '2026-08-14',
                    'note': ['invalid'],
                },
                'note-validation-expense',
            ),
            (
                '/api/accounting/dividends/',
                {
                    'total_cny': '1.00', 'business_date': '2026-08-14',
                    'note': {'invalid': True},
                },
                'note-validation-dividend',
            ),
        )
        self.client.raise_request_exception = False
        try:
            for path, payload, key in requests:
                with self.subTest(path=path):
                    response = self.request('post', path, payload, key=key)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json()['code'], 'input_error')
        finally:
            self.client.raise_request_exception = True

    def test_dividend_http_flow_warning_ack_replay_and_decimal_contract(self):
        self.complete_day1()
        accounts = []
        for suffix in ('a', 'b'):
            account = FundAccount.objects.create(
                name=f'动作分红账户 {suffix}', currency=FundAccount.Currency.CNY,
                creation_idempotency_key=f'action-dividend-account-{suffix}',
            )
            record_opening_balance(
                account, Decimal('100.00'), Decimal('100.00'),
                LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
                self.operator, f'action-dividend-opening-{suffix}',
            )
            accounts.append(account)

        created = self.request('post', '/api/accounting/dividends/', {
            'total_cny': '100.00', 'business_date': '2026-08-14',
        }, key='action-dividend-create')
        self.assertEqual(created.status_code, 201)
        dividend = created.json()['dividend']
        self.assertEqual(dividend['version'], 1)
        self.assertEqual(dividend['partner_a_amount_cny'], '50.00')
        self.assertEqual(dividend['partner_b_amount_cny'], '50.00')

        updated = self.request('patch', f"/api/accounting/dividends/{dividend['id']}/", {
            'total_cny': '80.00', 'partner_a_amount_cny': '30.00',
            'partner_b_amount_cny': '50.00', 'partner_a_account_id': accounts[0].pk,
            'partner_b_account_id': accounts[1].pk, 'expected_version': 1,
        }, key='action-dividend-update')
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['dividend']['version'], 2)
        self.assertEqual(updated.json()['dividend']['total_cny'], '80.00')

        preview = self.request(
            'post', f"/api/accounting/dividends/{dividend['id']}/preview/", {},
            key='action-dividend-preview',
        )
        self.assertEqual(preview.status_code, 200)
        preview_body = preview.json()['preview']
        self.assertEqual(preview_body['retained_earnings_cny'], '0.00')
        self.assertEqual(preview_body['requested_cny'], '80.00')
        self.assertEqual(preview_body['warning']['code'], 'retained_earnings_exceeded')
        warning_fingerprint = preview_body['warning_fingerprint']

        confirm_body = {
            'expected_version': 2, 'warning_fingerprint': warning_fingerprint,
            'warning_ack': False,
        }
        needs_ack = self.request(
            'post', f"/api/accounting/dividends/{dividend['id']}/confirm/", confirm_body,
            key='action-dividend-confirm-no-ack',
        )
        self.assertEqual(needs_ack.status_code, 409)
        self.assertEqual(needs_ack.json()['code'], 'warning_required')
        self.assertEqual(needs_ack.json()['details']['warning']['code'], 'retained_earnings_exceeded')

        confirm_body['warning_ack'] = True
        posted = self.request(
            'post', f"/api/accounting/dividends/{dividend['id']}/confirm/", confirm_body,
            key='action-dividend-confirm',
        )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()['dividend']['status'], 'posted')
        self.assertIsInstance(posted.json()['dividend']['total_cny'], str)
        ledger_count = LedgerTransaction.objects.filter(
            transaction_type=LedgerTransaction.TransactionType.DIVIDEND,
        ).count()
        self.assertEqual(ledger_count, 1)

        replay = self.request(
            'post', f"/api/accounting/dividends/{dividend['id']}/confirm/", confirm_body,
            key='action-dividend-confirm',
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()['dividend']['id'], dividend['id'])
        self.assertEqual(LedgerTransaction.objects.filter(
            transaction_type=LedgerTransaction.TransactionType.DIVIDEND,
        ).count(), ledger_count)
