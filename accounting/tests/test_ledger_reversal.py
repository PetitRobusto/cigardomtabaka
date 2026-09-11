from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounting import services as ledger_services
from accounting.models import Day1Initialization, FundAccount, LedgerPosting, LedgerTransaction
from accounting.selectors import account_snapshot
from accounting.services import (
    LedgerError, PostingInput, confirm_reconciliation, create_reconciliation,
    exchange_to_rub, post_transaction,
    record_opening_balance, reverse_exchange, transfer_same_currency,
)
from cigars.models import User


class LedgerReversalServiceTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            'reversal-operator', password='pass', is_staff=True,
        )
        self.other_operator = User.objects.create_user(
            'reversal-operator-b', password='pass', is_staff=True,
        )
        self.account = FundAccount.objects.create(
            name='冲正现金', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='reversal-cny',
        )

    def _posting(self, amount, cny_amount=None):
        amount = Decimal(amount)
        return PostingInput(
            account=self.account,
            currency=FundAccount.Currency.CNY,
            amount=amount,
            cny_amount=amount if cny_amount is None else Decimal(cny_amount),
        )

    def _category(self, category, amount):
        amount = Decimal(amount)
        return PostingInput(
            category=category,
            currency=FundAccount.Currency.CNY,
            amount=amount,
            cny_amount=amount,
        )

    def _original(self, *, key='reversal-original'):
        return post_transaction(
            transaction_type=LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
            business_date=date(2026, 8, 10),
            postings=[
                self._posting('100'),
                self._category(LedgerPosting.Category.SALES_REVENUE, '-100'),
            ],
            operator=self.operator,
            idempotency_key=key,
            description='原交易',
            source_type='test',
            source_id='original-source',
        )

    def _reverse(self, original, **changes):
        arguments = {
            'original_transaction': original,
            'business_date': date(2026, 8, 11),
            'operator': self.operator,
            'idempotency_key': 'reversal-key',
            'reason': '撤销原交易',
        }
        arguments.update(changes)
        return ledger_services.reverse_ledger_transaction(**arguments)

    def test_reversal_posts_opposite_account_and_category_entries(self):
        original = self._original()

        reversal = self._reverse(original)

        original.refresh_from_db()
        self.assertEqual(original.status, LedgerTransaction.Status.POSTED)
        self.assertEqual(original.reversed_by_id, reversal.pk)
        self.assertEqual(reversal.transaction_type, original.transaction_type)
        self.assertEqual(reversal.status, LedgerTransaction.Status.POSTED)
        self.assertEqual(reversal.source_type, 'ledger_reversal')
        self.assertEqual(reversal.source_id, str(original.pk))
        self.assertEqual(reversal.description, '撤销原交易')
        self.assertEqual(reversal.operator_id, self.operator.pk)
        self.assertEqual(
            list(reversal.postings.order_by('id').values_list(
                'account_id', 'category', 'amount', 'cny_amount',
            )),
            [
                (self.account.pk, '', Decimal('-100.00'), Decimal('-100.00')),
                (None, LedgerPosting.Category.SALES_REVENUE, Decimal('100.00'), Decimal('100.00')),
            ],
        )

    def test_reversal_replays_same_request_and_rejects_changed_request(self):
        original = self._original(key='reversal-replay-original')
        first = self._reverse(original)
        replay = self._reverse(original)

        self.assertEqual(replay.pk, first.pk)
        for changes in (
            {'reason': '改过的原因'},
            {'business_date': date(2026, 8, 12)},
            {'operator': self.other_operator},
            {'idempotency_key': 'another-reversal-key'},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(LedgerError):
                    self._reverse(original, **changes)
        self.assertEqual(
            LedgerTransaction.objects.filter(source_type='ledger_reversal').count(),
            1,
        )

    def test_reversal_rejects_unsupported_and_already_reversal_transactions(self):
        unsupported = post_transaction(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            business_date=date(2026, 8, 10),
            postings=[
                self._posting('10'),
                self._category(LedgerPosting.Category.SALES_REVENUE, '-10'),
            ],
            operator=self.operator,
            idempotency_key='unsupported-original',
            description='不允许冲正',
            source_type='test', source_id='unsupported',
        )
        with self.assertRaises(LedgerError):
            self._reverse(unsupported)

        original = self._original(key='reversal-source-original')
        reversal = self._reverse(original)
        with self.assertRaises(LedgerError):
            ledger_services.reverse_ledger_transaction(
                original_transaction=reversal,
                business_date=date(2026, 8, 12),
                operator=self.operator,
                idempotency_key='reverse-the-reversal',
                reason='禁止再次冲正',
            )

    def test_reversal_date_cannot_precede_original(self):
        original = self._original(key='reversal-date-original')
        with self.assertRaises(LedgerError):
            self._reverse(original, business_date=date(2026, 8, 9))
        original.refresh_from_db()
        self.assertIsNone(original.reversed_by_id)


class ExchangeReversalServiceTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            'exchange-reversal-operator', password='pass', is_staff=True,
        )
        Day1Initialization.objects.create(
            singleton_key='company', status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10), completed_by=self.operator,
        )
        self.cny = FundAccount.objects.create(
            name='换汇冲正人民币', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='exchange-reversal-cny',
        )
        self.rub = FundAccount.objects.create(
            name='换汇冲正卢布', currency=FundAccount.Currency.RUB,
            creation_idempotency_key='exchange-reversal-rub',
        )
        record_opening_balance(
            self.cny, '1000.00', '1000.00', LedgerPosting.Category.OPENING_CAPITAL,
            date(2026, 8, 10), self.operator, 'exchange-reversal-opening',
        )

    def _exchange(self, key='exchange-reversal-original'):
        return exchange_to_rub(
            self.cny, self.rub, '100.00', '1200.00', date(2026, 8, 11),
            self.operator, key,
        )

    def test_reverse_exchange_restores_both_original_currency_and_cny_cost(self):
        original = self._exchange()

        reversal = reverse_exchange(
            exchange_id=original.pk,
            business_date=date(2026, 8, 12),
            operator=self.operator,
            idempotency_key='exchange-reversal-action',
            reason='录入金额错误',
        )

        original.refresh_from_db()
        self.assertEqual(original.reversed_by_id, reversal.pk)
        self.assertEqual(reversal.transaction_type, LedgerTransaction.TransactionType.EXCHANGE)
        self.assertEqual(reversal.source_type, 'ledger_reversal')
        self.assertEqual(reversal.source_id, str(original.pk))
        self.assertEqual(account_snapshot(self.cny).original_balance, Decimal('1000.00'))
        self.assertEqual(account_snapshot(self.cny).cny_book_cost, Decimal('1000.00'))
        self.assertEqual(account_snapshot(self.rub).original_balance, Decimal('0.00'))
        self.assertEqual(account_snapshot(self.rub).cny_book_cost, Decimal('0.00'))

        replay = reverse_exchange(
            exchange_id=original.pk,
            business_date=date(2026, 8, 12),
            operator=self.operator,
            idempotency_key='exchange-reversal-action',
            reason='录入金额错误',
        )
        self.assertEqual(replay.pk, reversal.pk)
        self.assertEqual(
            LedgerTransaction.objects.filter(source_type='ledger_reversal').count(), 1,
        )

    def test_reverse_exchange_rejects_after_either_account_has_later_activity(self):
        original = self._exchange(key='exchange-reversal-used-original')
        target = FundAccount.objects.create(
            name='换汇冲正卢布转出目标', currency=FundAccount.Currency.RUB,
            creation_idempotency_key='exchange-reversal-rub-target',
        )
        transfer_same_currency(
            self.rub, target, '100.00', date(2026, 8, 12), self.operator,
            'exchange-reversal-later-transfer',
        )

        with self.assertRaises(LedgerError) as raised:
            reverse_exchange(
                exchange_id=original.pk,
                business_date=date(2026, 8, 13),
                operator=self.operator,
                idempotency_key='exchange-reversal-after-use',
                reason='不能破坏后续成本',
            )

        self.assertEqual(raised.exception.code, 'exchange_has_later_activity')
        original.refresh_from_db()
        self.assertIsNone(original.reversed_by_id)

    def test_reverse_exchange_rejects_a_later_inflow_to_the_target_account(self):
        original = self._exchange(key='exchange-reversal-later-inflow-original')
        exchange_to_rub(
            self.cny, self.rub, '50.00', '600.00', date(2026, 8, 12),
            self.operator, 'exchange-reversal-later-inflow',
        )

        with self.assertRaises(LedgerError) as raised:
            reverse_exchange(
                exchange_id=original.pk,
                business_date=date(2026, 8, 13),
                operator=self.operator,
                idempotency_key='exchange-reversal-after-inflow',
                reason='不能抽走已混合的历史成本',
            )

        self.assertEqual(raised.exception.code, 'exchange_has_later_activity')

    def test_generic_reversal_cannot_bypass_exchange_safety_checks(self):
        original = self._exchange(key='exchange-reversal-generic-bypass-original')

        with self.assertRaises(LedgerError):
            ledger_services.reverse_ledger_transaction(
                original_transaction=original,
                business_date=date(2026, 8, 12),
                operator=self.operator,
                idempotency_key='exchange-reversal-generic-bypass',
                reason='禁止绕过专用入口',
            )

        original.refresh_from_db()
        self.assertIsNone(original.reversed_by_id)

    def test_reverse_exchange_rejects_non_exchange_transaction(self):
        opening = LedgerTransaction.objects.get(idempotency_key='exchange-reversal-opening')

        with self.assertRaises(LedgerError) as raised:
            reverse_exchange(
                exchange_id=opening.pk,
                business_date=date(2026, 8, 12),
                operator=self.operator,
                idempotency_key='exchange-reversal-wrong-type',
                reason='错误目标',
            )

        self.assertEqual(raised.exception.code, 'exchange_not_found')

    def test_reverse_exchange_rejects_malformed_exchange_postings(self):
        target = FundAccount.objects.create(
            name='伪换汇人民币目标', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='exchange-reversal-malformed-target',
        )
        malformed = post_transaction(
            transaction_type=LedgerTransaction.TransactionType.EXCHANGE,
            business_date=date(2026, 8, 11),
            postings=[
                PostingInput(account=self.cny, currency='CNY', amount=Decimal('-10.00'), cny_amount=Decimal('-10.00')),
                PostingInput(account=target, currency='CNY', amount=Decimal('10.00'), cny_amount=Decimal('10.00')),
            ],
            operator=self.operator,
            idempotency_key='exchange-reversal-malformed-original',
        )

        with self.assertRaises(LedgerError) as raised:
            reverse_exchange(
                exchange_id=malformed.pk,
                business_date=date(2026, 8, 12),
                operator=self.operator,
                idempotency_key='exchange-reversal-malformed-action',
                reason='异常结构不能自动处理',
            )

        self.assertEqual(raised.exception.code, 'invalid_exchange_structure')

    def test_reverse_exchange_allows_inactive_accounts_for_correction(self):
        original = self._exchange(key='exchange-reversal-inactive-original')
        self.cny.is_active = False
        self.cny.save(update_fields=['is_active'])
        self.rub.is_active = False
        self.rub.save(update_fields=['is_active'])

        reversal = reverse_exchange(
            exchange_id=original.pk,
            business_date=date(2026, 8, 12),
            operator=self.operator,
            idempotency_key='exchange-reversal-inactive-action',
            reason='停用账户中的历史录入错误',
        )

        self.assertEqual(reversal.source_type, 'ledger_reversal')
        self.assertEqual(account_snapshot(self.cny).original_balance, Decimal('1000.00'))
        self.assertEqual(account_snapshot(self.rub).original_balance, Decimal('0.00'))

    def test_reverse_exchange_rejects_a_confirmed_reconciliation_on_reversal_date(self):
        original = self._exchange(key='exchange-reversal-reconciled-original')
        reconciliation = create_reconciliation(
            account=self.rub,
            business_date=date(2026, 8, 12),
            actual_amount='1200.00',
            operator=self.operator,
            idempotency_key='exchange-reversal-reconciliation-create',
        )
        confirm_reconciliation(
            reconciliation_id=reconciliation.pk,
            operator=self.operator,
            idempotency_key='exchange-reversal-reconciliation-confirm',
        )

        with self.assertRaises(LedgerError) as raised:
            reverse_exchange(
                exchange_id=original.pk,
                business_date=date(2026, 8, 12),
                operator=self.operator,
                idempotency_key='exchange-reversal-reconciled-action',
                reason='同日已完成对账',
            )

        self.assertEqual(raised.exception.code, 'exchange_reconciled_period')

    def test_usdt_exchange_reversal_restores_eight_place_balance_and_cny_cost(self):
        usdt = FundAccount.objects.create(
            name='换汇冲正 USDT', currency=FundAccount.Currency.USDT,
            creation_idempotency_key='exchange-reversal-usdt',
        )
        record_opening_balance(
            usdt, '10.12345678', '72.34', LedgerPosting.Category.OPENING_CAPITAL,
            date(2026, 8, 10), self.operator, 'exchange-reversal-usdt-opening',
        )
        original = exchange_to_rub(
            usdt, self.rub, '1.12345678', '100.00', date(2026, 8, 11),
            self.operator, 'exchange-reversal-usdt-original',
        )

        reverse_exchange(
            exchange_id=original.pk,
            business_date=date(2026, 8, 12),
            operator=self.operator,
            idempotency_key='exchange-reversal-usdt-action',
            reason='USDT 换汇录入错误',
        )

        self.assertEqual(account_snapshot(usdt).original_balance, Decimal('10.12345678'))
        self.assertEqual(account_snapshot(usdt).cny_book_cost, Decimal('72.34'))
        self.assertEqual(account_snapshot(self.rub).original_balance, Decimal('0.00'))
        self.assertEqual(account_snapshot(self.rub).cny_book_cost, Decimal('0.00'))
