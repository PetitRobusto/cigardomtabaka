from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from accounting.admin import (
    FundAccountAdmin,
    LedgerPostingAdmin,
    LedgerSequenceAdmin,
    LedgerTransactionAdmin,
)
from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction
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


class AccountingAdminTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('admin', password='pass', is_staff=True, is_superuser=True)
        self.request = RequestFactory().get('/admin/accounting/')
        self.request.user = self.user

        self.staff_user = User.objects.create_user('partner-admin', password='pass', is_staff=True)
        self.nonstaff_user = User.objects.create_user('customer', password='pass')
        self.staff_request = RequestFactory().get('/admin/accounting/')
        self.staff_request.user = self.staff_user
        self.nonstaff_request = RequestFactory().get('/admin/accounting/')
        self.nonstaff_request.user = self.nonstaff_user
        self.account = FundAccount.objects.create(
            name='后台账户',
            currency=FundAccount.Currency.CNY,
            creation_idempotency_key='admin-account',
        )
    def test_ledger_records_are_registered_as_read_only_and_cannot_be_added_or_deleted(self):
        for model, admin_class in (
            (LedgerTransaction, LedgerTransactionAdmin),
            (LedgerPosting, LedgerPostingAdmin),
            (LedgerSequence, LedgerSequenceAdmin),
        ):
            with self.subTest(model=model.__name__):
                model_admin = admin_class(model, AdminSite())

                self.assertFalse(model_admin.has_add_permission(self.request))
                self.assertFalse(model_admin.has_delete_permission(self.request))
                self.assertEqual(model_admin.get_actions(self.request), {})
                self.assertTrue(model_admin.has_change_permission(self.request))
                self.assertTrue(
                    set(field.name for field in model._meta.fields).issubset(
                        set(model_admin.get_readonly_fields(self.request)),
                    ),
                )
                self.assertEqual(
                    model_admin.get_form(self.request).base_fields,
                    {},
                )

        self.assertIsInstance(admin.site._registry[FundAccount], FundAccountAdmin)
        self.assertIsInstance(admin.site._registry[LedgerTransaction], LedgerTransactionAdmin)
        self.assertIsInstance(admin.site._registry[LedgerPosting], LedgerPostingAdmin)
        self.assertIsInstance(admin.site._registry[LedgerSequence], LedgerSequenceAdmin)

    def test_fund_account_admin_keeps_metadata_editable_and_displays_derived_balances(self):
        model_admin = FundAccountAdmin(FundAccount, AdminSite())
        editable_metadata = {'name', 'currency', 'custodian', 'creation_idempotency_key', 'is_active'}
        # 账户创建后的可变元数据仅限名称、保管人和启用状态。
        editable_metadata = {'name', 'custodian', 'is_active'}


        self.assertTrue(editable_metadata.issubset(model_admin.get_form(self.request).base_fields))
        self.assertTrue({'original_balance', 'cny_book_cost'}.issubset(model_admin.get_readonly_fields(self.request)))
        self.assertTrue(
            {'name', 'currency', 'custodian', 'is_active', 'original_balance', 'cny_book_cost'}
            .issubset(model_admin.list_display),
        )

    def test_only_staff_can_view_or_change_any_accounting_admin(self):
        for model, admin_class in (
            (FundAccount, FundAccountAdmin),
            (LedgerTransaction, LedgerTransactionAdmin),
            (LedgerPosting, LedgerPostingAdmin),
            (LedgerSequence, LedgerSequenceAdmin),
        ):
            with self.subTest(model=model.__name__):
                model_admin = admin_class(model, AdminSite())

                self.assertTrue(model_admin.has_module_permission(self.staff_request))
                self.assertTrue(model_admin.has_view_permission(self.staff_request))
                self.assertTrue(model_admin.has_change_permission(self.staff_request))
                self.assertFalse(model_admin.has_module_permission(self.nonstaff_request))
                self.assertFalse(model_admin.has_view_permission(self.nonstaff_request))
                self.assertFalse(model_admin.has_change_permission(self.nonstaff_request))
                self.assertFalse(model_admin.has_add_permission(self.staff_request))
                self.assertFalse(model_admin.has_delete_permission(self.staff_request))
                self.assertIsNone(model_admin.actions)
                self.assertEqual(model_admin.get_actions(self.staff_request), {})

    def test_fund_account_admin_only_allows_mutable_metadata_and_admin_post_preserves_keys(self):
        model_admin = FundAccountAdmin(FundAccount, AdminSite())

        self.assertEqual(
            set(model_admin.get_form(self.staff_request).base_fields),
            {'name', 'custodian', 'is_active'},
        )
        self.assertTrue(
            {'currency', 'creation_idempotency_key', 'created_at', 'original_balance', 'cny_book_cost'}
            .issubset(model_admin.get_readonly_fields(self.staff_request)),
        )

        self.client.force_login(self.staff_user)
        response = self.client.post(
            f'/admin/accounting/fundaccount/{self.account.pk}/change/',
            {'name': '已更名账户', 'custodian': '', 'is_active': 'on', '_save': '保存'},
        )

        self.assertEqual(response.status_code, 302)
        self.account.refresh_from_db()
        self.assertEqual(self.account.name, '已更名账户')
        self.assertEqual(self.account.currency, FundAccount.Currency.CNY)
        self.assertEqual(self.account.creation_idempotency_key, 'admin-account')

    def test_fund_account_list_uses_posted_balance_annotations_without_per_row_queries(self):
        second_account = FundAccount.objects.create(
            name='第二后台账户',
            currency=FundAccount.Currency.CNY,
            creation_idempotency_key='second-admin-account',
        )
        posted = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.OPENING_BALANCE,
            status=LedgerTransaction.Status.POSTED,
            business_date=date(2026, 8, 10),
            effective_sequence=1,
            operator=self.user,
        )
        LedgerPosting.objects.create(
            transaction=posted,
            account=self.account,
            currency=FundAccount.Currency.CNY,
            amount=Decimal('12.00'),
            cny_amount=Decimal('12.00'),
        )
        LedgerPosting.objects.create(
            transaction=posted,
            category=LedgerPosting.Category.OPENING_CAPITAL,
            currency=FundAccount.Currency.CNY,
            amount=Decimal('-12.00'),
            cny_amount=Decimal('-12.00'),
        )
        draft = LedgerTransaction.objects.create(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            status=LedgerTransaction.Status.DRAFT,
            business_date=date(2026, 8, 10),
            operator=self.user,
        )
        LedgerPosting.objects.create(
            transaction=draft,
            account=self.account,
            currency=FundAccount.Currency.CNY,
            amount=Decimal('99.00'),
            cny_amount=Decimal('99.00'),
        )

        model_admin = FundAccountAdmin(FundAccount, AdminSite())
        queryset = model_admin.get_queryset(self.staff_request).order_by('pk')

        self.assertIn('admin_original_balance', queryset.query.annotations)
        self.assertIn('admin_cny_book_cost', queryset.query.annotations)
        with self.assertNumQueries(1):
            accounts = {account.pk: account for account in queryset}
        with self.assertNumQueries(0):
            self.assertEqual(model_admin.original_balance(accounts[self.account.pk]), '12.00000000')
            self.assertEqual(model_admin.cny_book_cost(accounts[self.account.pk]), '12.00')
            self.assertEqual(model_admin.original_balance(accounts[second_account.pk]), '0.00000000')
            self.assertEqual(model_admin.cny_book_cost(accounts[second_account.pk]), '0.00')
