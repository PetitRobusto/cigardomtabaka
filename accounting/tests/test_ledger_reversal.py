from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounting import services as ledger_services
from accounting.models import FundAccount, LedgerPosting, LedgerTransaction
from accounting.services import LedgerError, PostingInput, post_transaction
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
