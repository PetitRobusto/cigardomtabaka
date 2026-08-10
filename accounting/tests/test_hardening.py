from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.models import FundAccount, LedgerPosting, LedgerSequence, LedgerTransaction
from accounting.services import LedgerError, PostingInput, post_transaction
from cigars.models import User


class LedgerHardeningTest(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user('hardening-operator', password='pass', is_staff=True)
        self.account = FundAccount.objects.create(name='Hardening CNY', currency='CNY', creation_idempotency_key='hardening-cny')

    def post(self, key='hardening-posted'):
        return post_transaction(
            transaction_type=LedgerTransaction.TransactionType.TRANSFER,
            business_date=date(2026, 8, 10), operator=self.operator, idempotency_key=key,
            postings=[
                PostingInput(account=self.account, currency='CNY', amount=Decimal('100'), cny_amount=Decimal('100')),
                PostingInput(category=LedgerPosting.Category.OPENING_CAPITAL, currency='CNY', amount=Decimal('-100'), cny_amount=Decimal('-100')),
            ],
        )

    def test_direct_posted_transaction_creation_is_rejected(self):
        fields = dict(transaction_type='transfer', status='posted', business_date=date(2026, 8, 10), effective_sequence=1, operator=self.operator)
        with self.assertRaises(ValidationError):
            LedgerTransaction.objects.create(**fields)
        with self.assertRaises(ValidationError):
            LedgerTransaction.objects.bulk_create([LedgerTransaction(**fields)])

    def test_public_post_rejects_single_and_unbalanced_postings(self):
        cases = [
            [PostingInput(account=self.account, currency='CNY', amount=Decimal('100'), cny_amount=Decimal('100'))],
            [
                PostingInput(account=self.account, currency='CNY', amount=Decimal('100'), cny_amount=Decimal('100')),
                PostingInput(category='opening_capital', currency='CNY', amount=Decimal('-99'), cny_amount=Decimal('-99')),
            ],
        ]
        for index, postings in enumerate(cases):
            with self.subTest(postings=postings), self.assertRaises(LedgerError):
                post_transaction(
                    transaction_type='transfer', business_date=date(2026, 8, 10),
                    postings=postings, operator=self.operator, idempotency_key=f'invalid-post-{index}',
                )

    def test_posted_records_reject_instance_queryset_and_bulk_mutations(self):
        posted = self.post()
        posting = posted.postings.get(account=self.account)
        posted.description = 'tampered'
        posting.amount = Decimal('99')
        operations = [
            lambda: posted.save(), lambda: posted.delete(),
            lambda: LedgerTransaction.objects.filter(pk=posted.pk).update(description='tampered'),
            lambda: LedgerTransaction.objects.filter(pk=posted.pk).delete(),
            lambda: LedgerTransaction.objects.bulk_update([posted], ['description']),
            lambda: posting.save(), lambda: posting.delete(),
            lambda: LedgerPosting.objects.filter(pk=posting.pk).update(amount=Decimal('99')),
            lambda: LedgerPosting.objects.filter(pk=posting.pk).delete(),
            lambda: LedgerPosting.objects.bulk_update([posting], ['amount']),
            lambda: LedgerPosting.objects.create(transaction=posted, account=self.account, currency='CNY', amount=Decimal('1'), cny_amount=Decimal('1')),
            lambda: LedgerPosting.objects.bulk_create([LedgerPosting(transaction=posted, account=self.account, currency='CNY', amount=Decimal('1'), cny_amount=Decimal('1'))]),
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()

    def test_public_opening_balance_cannot_bypass_business_rules(self):
        def opening(account, key, day=date(2026, 8, 10)):
            return post_transaction(transaction_type='opening_balance', business_date=day, operator=self.operator, idempotency_key=key, postings=[
                PostingInput(account=account, currency='CNY', amount=Decimal('100'), cny_amount=Decimal('100')),
                PostingInput(category='opening_capital', currency='CNY', amount=Decimal('-100'), cny_amount=Decimal('-100')),
            ])
        with self.assertRaises(LedgerError):
            opening(self.account, 'next-day', date(2026, 8, 11))
        other = FundAccount.objects.create(name='Hardening second', currency='CNY', creation_idempotency_key='hardening-second')
        with self.assertRaises(LedgerError):
            post_transaction(transaction_type='opening_balance', business_date=date(2026, 8, 10), operator=self.operator, idempotency_key='many-accounts', postings=[
                PostingInput(account=self.account, currency='CNY', amount=Decimal('50'), cny_amount=Decimal('50')),
                PostingInput(account=other, currency='CNY', amount=Decimal('50'), cny_amount=Decimal('50')),
                PostingInput(category='opening_capital', currency='CNY', amount=Decimal('-100'), cny_amount=Decimal('-100')),
            ])
        first = opening(self.account, 'first-opening')
        self.assertEqual(opening(self.account, 'first-opening').pk, first.pk)
        with self.assertRaises(LedgerError):
            opening(self.account, 'used-account')
        post_transaction(transaction_type='transfer', business_date=date(2026, 8, 10), operator=self.operator, idempotency_key='ordinary', postings=[
            PostingInput(account=self.account, currency='CNY', amount=Decimal('-1'), cny_amount=Decimal('-1')),
            PostingInput(account=other, currency='CNY', amount=Decimal('1'), cny_amount=Decimal('1')),
        ])
        third = FundAccount.objects.create(name='Hardening third', currency='CNY', creation_idempotency_key='hardening-third')
        with self.assertRaises(LedgerError):
            opening(third, 'after-ordinary')

    def test_persisted_posted_state_cannot_be_hidden_in_memory(self):
        posted = self.post('persisted-state')
        posted.status = LedgerTransaction.Status.DRAFT
        with self.assertRaises(ValidationError):
            posted.save()

        draft = LedgerTransaction.objects.create(
            transaction_type='transfer', business_date=date(2026, 8, 10), operator=self.operator,
        )
        posting = posted.postings.get(account=self.account)
        posting.transaction = draft
        with self.assertRaises(ValidationError):
            posting.save()
        with self.assertRaises(ValidationError):
            posting.delete()

    def test_no_direct_posting_capability_is_exposed(self):
        import accounting.models as ledger_models

        self.assertFalse(hasattr(ledger_models, '_post_draft_transaction'))
        self.assertFalse(hasattr(LedgerTransaction, 'transition_to_posted'))

    def test_ordinary_callers_have_no_ledger_mutation_capabilities(self):
        import accounting.models as ledger_models

        self.assertFalse(hasattr(ledger_models, 'ledger_mutation'))
        self.assertFalse(hasattr(ledger_models, 'ledger_posting_transition'))

    def test_queryset_status_expression_and_base_manager_cannot_bypass_guards(self):
        from django.db.models import Value

        posted = self.post('manager-guard')
        posting = posted.postings.get(account=self.account)
        draft = LedgerTransaction.objects.create(
            transaction_type='transfer', business_date=date(2026, 8, 10), operator=self.operator,
        )
        operations = [
            lambda: LedgerTransaction.objects.filter(pk=draft.pk).update(status=Value('posted')),
            lambda: LedgerTransaction._base_manager.filter(pk=posted.pk).update(description='tampered'),
            lambda: LedgerTransaction._base_manager.filter(pk=posted.pk).delete(),
            lambda: LedgerPosting._base_manager.filter(pk=posting.pk).update(amount=Decimal('99')),
            lambda: LedgerPosting._base_manager.filter(pk=posting.pk).delete(),
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()

    def test_public_opening_rejects_nonpositive_account_amounts(self):
        for amount in ('0', '-1'):
            with self.subTest(amount=amount), self.assertRaises(LedgerError):
                post_transaction(
                    transaction_type='opening_balance', business_date=date(2026, 8, 10),
                    operator=self.operator, idempotency_key=f'opening-{amount}',
                    postings=[
                        PostingInput(account=self.account, currency='CNY', amount=Decimal(amount), cny_amount=Decimal(amount)),
                        PostingInput(category='opening_capital', currency='CNY', amount=-Decimal(amount), cny_amount=-Decimal(amount)),
                    ],
                )
        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_postings_cannot_be_rebound_to_a_posted_transaction(self):
        posted = self.post("posted-target")
        draft = LedgerTransaction.objects.create(transaction_type="transfer", business_date=date(2026, 8, 10), operator=self.operator)
        draft_posting = LedgerPosting.objects.create(transaction=draft, account=self.account, currency="CNY", amount=Decimal("1"), cny_amount=Decimal("1"))
        operations = [
            lambda: LedgerPosting.objects.filter(pk=draft_posting.pk).update(transaction=posted),
            lambda: LedgerPosting._base_manager.filter(pk=draft_posting.pk).update(transaction_id=posted.pk),
            lambda: LedgerPosting.objects.bulk_update([draft_posting], ["transaction"]),
            lambda: posted.postings.add(draft_posting, bulk=True),
            lambda: posted.postings.add(draft_posting, bulk=False),
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()

    def test_ordinary_orm_cannot_create_or_change_status_with_expressions(self):
        from django.db.models import Value

        fields = dict(transaction_type='transfer', business_date=date(2026, 8, 10), operator=self.operator)
        with self.assertRaises(ValidationError):
            LedgerTransaction.objects.create(status=Value('posted'), **fields)
        with self.assertRaises(ValidationError):
            LedgerTransaction.objects.create(status=LedgerTransaction.Status.REVERSED, **fields)
        draft = LedgerTransaction.objects.create(status=LedgerTransaction.Status.DRAFT, **fields)
        draft.status = Value('posted')
        with self.assertRaises(ValidationError):
            draft.save()
        with self.assertRaises(ValidationError):
            LedgerTransaction.objects.bulk_create([
                LedgerTransaction(status=Value('posted'), **fields),
            ])

    def test_reversed_transactions_and_postings_are_immutable(self):
        from django.db import connection

        transaction = self.post('reversed-immutable')
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE accounting_ledgertransaction SET status = %s WHERE id = %s',
                [LedgerTransaction.Status.REVERSED, transaction.pk],
            )
        transaction.refresh_from_db()
        posting = transaction.postings.get(account=self.account)
        transaction.description = 'tampered'
        operations = [
            lambda: transaction.save(),
            lambda: transaction.delete(),
            lambda: LedgerTransaction.objects.filter(pk=transaction.pk).update(description='tampered'),
            lambda: LedgerTransaction._base_manager.filter(pk=transaction.pk).delete(),
            lambda: posting.save(),
            lambda: posting.delete(),
            lambda: LedgerPosting.objects.filter(pk=posting.pk).update(amount=Decimal('99')),
            lambda: LedgerPosting._base_manager.filter(pk=posting.pk).delete(),
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()

        transaction.status = LedgerTransaction.Status.DRAFT
        with self.assertRaises(ValidationError):
            transaction.delete()

    def test_draft_bulk_generators_are_materialized_without_losing_rows(self):
        transaction = LedgerTransaction(
            transaction_type='transfer', business_date=date(2026, 8, 10), operator=self.operator,
            idempotency_key='generator-draft', description='before',
        )
        LedgerTransaction.objects.bulk_create(item for item in [transaction])
        transaction.description = 'after'
        LedgerTransaction.objects.bulk_update((item for item in [transaction]), (field for field in ['description']))
        self.assertEqual(LedgerTransaction.objects.get(pk=transaction.pk).description, 'after')

        posting = LedgerPosting.objects.create(
            transaction=transaction, account=self.account, currency='CNY', amount=Decimal('1'), cny_amount=Decimal('1'),
        )
        posting.amount = Decimal('2')
        LedgerPosting.objects.bulk_update((item for item in [posting]), (field for field in ['amount']))
        self.assertEqual(LedgerPosting.objects.get(pk=posting.pk).amount, Decimal('2.00000000'))

    def test_fund_account_currency_and_creation_key_are_immutable_after_create(self):
        account = self.account
        account.currency = 'RUB'
        with self.assertRaises(ValidationError):
            account.save()
        expression_account = FundAccount.objects.get(pk=account.pk)
        from django.db.models import Value
        expression_account.currency = Value('RUB')
        with self.assertRaises(ValidationError):
            expression_account.save()
        operations = [
            lambda: FundAccount.objects.filter(pk=account.pk).update(currency='RUB'),
            lambda: FundAccount._base_manager.filter(pk=account.pk).update(creation_idempotency_key='changed'),
            lambda: FundAccount.objects.bulk_update([account], ['currency']),
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()
        account.refresh_from_db()
        account.name = 'renamed'
        account.is_active = False
        account.save()
        self.assertEqual(FundAccount.objects.get(pk=account.pk).name, 'renamed')

    def test_ledger_sequence_is_internal_except_initial_global_row(self):
        sequence, created = LedgerSequence.objects.get_or_create(name='global')
        self.assertTrue(created)
        operations = [
            lambda: sequence.save(),
            lambda: sequence.delete(),
            lambda: LedgerSequence.objects.filter(name='global').update(next_value=2),
            lambda: LedgerSequence._base_manager.filter(name='global').delete(),
            lambda: LedgerSequence.objects.bulk_update([sequence], ['next_value']),
            lambda: LedgerSequence.objects.bulk_create([LedgerSequence(name='other', next_value=1)]),
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                operation()

        transaction = self.post('sequence-service-increment')
        self.assertEqual(LedgerSequence.objects.get(name='global').next_value, transaction.effective_sequence + 1)

    def test_transaction_bulk_upsert_cannot_modify_finalized_transaction(self):
        posted = self.post('transaction-upsert-guard')
        candidate = LedgerTransaction(
            transaction_type='transfer',
            status=LedgerTransaction.Status.DRAFT,
            business_date=date(2026, 8, 10),
            operator=self.operator,
            idempotency_key=posted.idempotency_key,
            description='tampered',
        )
        with self.assertRaises(ValidationError):
            LedgerTransaction.objects.bulk_create(
                [candidate],
                update_conflicts=True,
                update_fields=['status', 'description'],
                unique_fields=['idempotency_key'],
            )
        posted.refresh_from_db()
        self.assertEqual(posted.status, LedgerTransaction.Status.POSTED)
        self.assertNotEqual(posted.description, 'tampered')

    def test_account_bulk_upsert_cannot_modify_immutable_fields_even_via_base_manager(self):
        for manager in (FundAccount.objects, FundAccount._base_manager):
            candidate = FundAccount(
                name=self.account.name,
                currency='RUB',
                creation_idempotency_key=self.account.creation_idempotency_key,
            )
            with self.subTest(manager=manager), self.assertRaises(ValidationError):
                manager.bulk_create(
                    [candidate],
                    update_conflicts=True,
                    update_fields=['currency'],
                    unique_fields=['creation_idempotency_key'],
                )
        self.account.refresh_from_db()
        self.assertEqual(self.account.currency, 'CNY')

    def test_account_bulk_upsert_allows_mutable_name_fields(self):
        candidate = FundAccount(
            name=self.account.name,
            currency=self.account.currency,
            creation_idempotency_key=self.account.creation_idempotency_key,
            is_active=False,
        )
        FundAccount.objects.bulk_create(
            [candidate],
            update_conflicts=True,
            update_fields=(field for field in ['is_active']),
            unique_fields=['creation_idempotency_key'],
        )
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)
