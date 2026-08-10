from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounting.models import FundAccount, LedgerPosting, LedgerTransaction
from cigars.models import User


class LedgerModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('partner-a', password='pass', is_staff=True)
        self.account = FundAccount.objects.create(
            name='合伙人 A 人民币',
            currency=FundAccount.Currency.CNY,
            custodian=self.user,
            creation_idempotency_key='account-a-cny',
        )

    def test_account_name_and_creation_key_are_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            FundAccount.objects.create(
                name=self.account.name,
                currency=FundAccount.Currency.CNY,
                creation_idempotency_key='other-key',
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            FundAccount.objects.create(
                name='另一个账户',
                currency=FundAccount.Currency.CNY,
                creation_idempotency_key='account-a-cny',
            )

    def test_posting_requires_exactly_one_target(self):
        tx = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
            status=LedgerTransaction.Status.POSTED,
            business_date=date(2026, 8, 10),
            effective_sequence=1,
            operator=self.user,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerPosting.objects.create(
                transaction=tx,
                account=self.account,
                category=LedgerPosting.Category.OPENING_CAPITAL,
                currency=FundAccount.Currency.CNY,
                amount=Decimal('1.00'),
                cny_amount=Decimal('1.00'),
            )

    def test_effective_sequence_and_idempotency_key_are_unique(self):
        LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
            status=LedgerTransaction.Status.POSTED,
            business_date=date(2026, 8, 10),
            effective_sequence=1,
            idempotency_key='opening-a',
            operator=self.user,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerTransaction.objects.create(
                transaction_type=LedgerTransaction.TransactionType.TRANSFER,
                status=LedgerTransaction.Status.POSTED,
                business_date=date(2026, 8, 10),
                effective_sequence=1,
                idempotency_key='other-operation',
                operator=self.user,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerTransaction.objects.create(
                transaction_type=LedgerTransaction.TransactionType.TRANSFER,
                status=LedgerTransaction.Status.POSTED,
                business_date=date(2026, 8, 10),
                effective_sequence=2,
                idempotency_key='opening-a',
                operator=self.user,
            )
