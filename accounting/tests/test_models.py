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

    def test_posting_target_xor(self):
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

        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerPosting.objects.create(
                transaction=tx,
                currency=FundAccount.Currency.CNY,
                amount=Decimal('1.00'),
                cny_amount=Decimal('1.00'),
            )

        account_posting = LedgerPosting.objects.create(
            transaction=tx,
            account=self.account,
            currency=FundAccount.Currency.CNY,
            amount=Decimal('1.00'),
            cny_amount=Decimal('1.00'),
        )
        category_posting = LedgerPosting.objects.create(
            transaction=tx,
            category=LedgerPosting.Category.OPENING_CAPITAL,
            currency=FundAccount.Currency.CNY,
            amount=Decimal('1.00'),
            cny_amount=Decimal('1.00'),
        )

        self.assertEqual(account_posting.account, self.account)
        self.assertEqual(account_posting.category, '')
        self.assertIsNone(category_posting.account)
        self.assertEqual(
            category_posting.category,
            LedgerPosting.Category.OPENING_CAPITAL,
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

    def test_optional_idempotency_keys_allow_multiple_nulls_and_blank_values(self):
        missing_key = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
            status=LedgerTransaction.Status.POSTED,
            business_date=date(2026, 8, 10),
            effective_sequence=1,
            operator=self.user,
        )
        another_missing_key = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            status=LedgerTransaction.Status.POSTED,
            business_date=date(2026, 8, 10),
            effective_sequence=2,
            operator=self.user,
        )
        blank_key = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            status=LedgerTransaction.Status.POSTED,
            business_date=date(2026, 8, 10),
            effective_sequence=3,
            idempotency_key='',
            operator=self.user,
        )
        another_blank_key = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            status=LedgerTransaction.Status.POSTED,
            business_date=date(2026, 8, 10),
            effective_sequence=4,
            idempotency_key='',
            operator=self.user,
        )

        self.assertIsNone(missing_key.idempotency_key)
        self.assertIsNone(another_missing_key.idempotency_key)
        self.assertIsNone(blank_key.idempotency_key)
        self.assertIsNone(another_blank_key.idempotency_key)

    def test_database_rejects_empty_idempotency_key(self):
        ledger_transaction = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
            status=LedgerTransaction.Status.POSTED,
            business_date=date(2026, 8, 10),
            effective_sequence=1,
            operator=self.user,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerTransaction.objects.filter(pk=ledger_transaction.pk).update(
                idempotency_key='',
            )
