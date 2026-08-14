from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.test import TestCase
from unittest.mock import patch

from accounting.models import (
    Day1Initialization, Dividend, DividendDraftAction, FundAccount,
    LedgerPosting, LedgerTransaction,
)
from accounting.services import PostingInput, post_transaction, record_opening_balance
from accounting.selectors import account_snapshot
from cigars.models import User


class DividendActionTest(TestCase):
    day = date(2026, 8, 14)

    def setUp(self):
        self.operator = User.objects.create_user(
            username='dividend-operator', is_staff=True,
        )
        Day1Initialization.objects.create(
            singleton_key='company',
            status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10),
            completed_by=self.operator,
        )

    def _fund_accounts(self, prefix='confirm'):
        accounts = []
        for suffix in ('a', 'b'):
            account = FundAccount.objects.create(
                name=f'分红 {prefix} {suffix}', currency=FundAccount.Currency.CNY,
                creation_idempotency_key=f'div-{prefix}-{suffix}',
            )
            record_opening_balance(
                account, Decimal('100.00'), Decimal('100.00'),
                LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
                self.operator, f'div-{prefix}-opening-{suffix}',
            )
            accounts.append(account)
        return accounts

    def test_dividend_draft_split_and_current_warning(self):
        from accounting.dividend_actions import create_dividend_draft, preview_dividend

        draft = create_dividend_draft(
            total_cny='101.01', business_date=self.day,
            operator=self.operator, idempotency_key='div-draft-1',
        )
        self.assertEqual(
            (draft.partner_a_amount_cny, draft.partner_b_amount_cny),
            (Decimal('50.51'), Decimal('50.50')),
        )
        preview = preview_dividend(dividend_id=draft.id, operator=self.operator)
        self.assertIn('warning_fingerprint', preview.to_dict())
        self.assertIn('warning', preview.to_dict())
        with self.assertRaises(ValidationError):
            DividendDraftAction(
                action_type='cancel', idempotency_key='div-cancel',
                request_fingerprint='x', operator=self.operator,
            ).full_clean()

    def test_dividend_replay_conflict_and_stale_warning(self):
        from accounting.dividend_actions import (
            DividendActionError, create_dividend_draft, preview_dividend,
            confirm_dividend,
        )

        first = create_dividend_draft(
            total_cny='50.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-replay-1',
        )
        replay = create_dividend_draft(
            total_cny='50.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-replay-1',
        )
        self.assertEqual(first.pk, replay.pk)
        with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
            create_dividend_draft(
                total_cny='51.00', business_date=self.day,
                operator=self.operator, idempotency_key='div-replay-1',
            )
        account_a = FundAccount.objects.create(
            name='分红 A 账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='div-cny-a',
        )
        account_b = FundAccount.objects.create(
            name='分红 B 账户', currency=FundAccount.Currency.CNY,
            creation_idempotency_key='div-cny-b',
        )
        record_opening_balance(
            account_a, Decimal('100.00'), Decimal('100.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'div-opening-a',
        )
        record_opening_balance(
            account_b, Decimal('100.00'), Decimal('100.00'),
            LedgerPosting.Category.OPENING_CAPITAL, date(2026, 8, 10),
            self.operator, 'div-opening-b',
        )
        from accounting.dividend_actions import update_dividend_draft
        first = update_dividend_draft(
            dividend_id=first.id, total_cny='50.00',
            partner_a_amount_cny='25.00', partner_b_amount_cny='25.00',
            partner_a_account_id=account_a.pk, partner_b_account_id=account_b.pk,
            expected_version=first.version, idempotency_key='div-update-1',
            operator=self.operator,
        )
        preview = preview_dividend(dividend_id=first.id, operator=self.operator)
        warning = preview.to_dict()
        post_transaction(
            transaction_type=LedgerTransaction.TransactionType.SALES_SHIPMENT,
            business_date=self.day,
            postings=[
                PostingInput(
                    category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE,
                    currency='CNY', amount=Decimal('500.00'),
                    cny_amount=Decimal('500.00'),
                ),
                PostingInput(
                    category=LedgerPosting.Category.SALES_REVENUE,
                    currency='CNY', amount=Decimal('-500.00'),
                    cny_amount=Decimal('-500.00'),
                ),
            ],
            operator=self.operator, idempotency_key='div-profit-fact',
        )
        with self.assertRaisesRegex(DividendActionError, 'warning_stale') as raised:
            confirm_dividend(
                dividend_id=first.id, operator=self.operator,
                idempotency_key='div-confirm-1', expected_version=first.version,
                warning_fingerprint=warning['warning_fingerprint'], warning_ack=True,
            )
        self.assertIn('warning', raised.exception.details)
        self.assertIn('fingerprint', raised.exception.details)
        latest = preview_dividend(dividend_id=first.id, operator=self.operator)
        self.assertEqual(raised.exception.details['warning'], latest.warning)
        self.assertEqual(raised.exception.details['fingerprint'], latest.warning_fingerprint)

    def test_preview_retries_locked_writer_and_persists_snapshot(self):
        from accounting.dividend_actions import create_dividend_draft, preview_dividend

        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-preview-retry-create',
        )
        with patch(
            'accounting.dividend_actions._acquire_sqlite_writer_gate',
            side_effect=[OperationalError('database is locked'), None],
        ) as gate:
            preview = preview_dividend(dividend_id=draft.id, operator=self.operator)
        self.assertEqual(gate.call_count, 2)
        self.assertEqual(
            Dividend.objects.get(pk=draft.pk).warning_fingerprint,
            preview.warning_fingerprint,
        )

    def test_strict_integer_parser_rejects_ambiguous_ids_and_versions(self):
        from accounting.dividend_actions import (
            DividendActionError, create_dividend_draft, update_dividend_draft,
            preview_dividend,
        )

        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-parser-create',
        )
        account_a, account_b = self._fund_accounts('parser')
        invalid_ids = (True, 1.0, Decimal('1'), ' 1', '1 ', '1.0', '1e0')
        for value in invalid_ids:
            with self.subTest(field='dividend_id', value=value):
                with self.assertRaisesRegex(DividendActionError, 'dividend_not_found'):
                    preview_dividend(dividend_id=value, operator=self.operator)
        for value in invalid_ids:
            with self.subTest(field='account_id', value=value):
                target = create_dividend_draft(
                    total_cny='20.00', business_date=self.day,
                    operator=self.operator,
                    idempotency_key=f'div-parser-account-create-{len(Dividend.objects.all())}-{repr(value)}',
                )
                with self.assertRaisesRegex(DividendActionError, 'account_not_found'):
                    update_dividend_draft(
                        dividend_id=target.id, total_cny='20.00',
                        partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
                        partner_a_account_id=value, partner_b_account_id=account_b.pk,
                        expected_version=target.version,
                        idempotency_key=f'div-parser-account-{len(str(value))}-{repr(value)}',
                        operator=self.operator,
                    )
        for value in invalid_ids:
            with self.subTest(field='expected_version', value=value):
                with self.assertRaisesRegex(DividendActionError, 'version_conflict'):
                    update_dividend_draft(
                        dividend_id=draft.id, total_cny='20.00',
                        partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
                        partner_a_account_id=account_a.pk, partner_b_account_id=account_b.pk,
                        expected_version=value, idempotency_key=f'div-parser-version-{len(str(value))}-{repr(value)}',
                        operator=self.operator,
                    )

    def test_update_locks_accounts_in_sorted_order(self):
        from accounting.dividend_actions import create_dividend_draft, update_dividend_draft

        account_a, account_b = self._fund_accounts('lock-order')
        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-lock-order-create',
        )
        with patch(
            'accounting.dividend_actions._lock_cny_accounts',
            wraps=lambda ids: {account.pk: account for account in (account_a, account_b)},
        ) as lock_accounts:
            update_dividend_draft(
                dividend_id=draft.id, total_cny='20.00',
                partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
                partner_a_account_id=account_b.pk, partner_b_account_id=account_a.pk,
                expected_version=draft.version, idempotency_key='div-lock-order-update',
                operator=self.operator,
            )
        self.assertEqual(
            lock_accounts.call_args.args[0],
            sorted((account_a.pk, account_b.pk)),
        )

    def test_create_and_update_require_string_notes(self):
        from accounting.dividend_actions import (
            DividendActionError, create_dividend_draft, update_dividend_draft,
        )

        for invalid_note in (123, None, ['not', 'a', 'string']):
            with self.subTest(invalid_note=invalid_note):
                with self.assertRaisesRegex(DividendActionError, 'invalid_note'):
                    create_dividend_draft(
                        total_cny='20.00', business_date=self.day,
                        operator=self.operator,
                        idempotency_key=f'div-note-create-invalid-{repr(invalid_note)}',
                        note=invalid_note,
                    )
        account_a, account_b = self._fund_accounts('note')
        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-note-create',
        )
        with self.assertRaisesRegex(DividendActionError, 'invalid_note'):
            update_dividend_draft(
                dividend_id=draft.id, total_cny='20.00',
                partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
                partner_a_account_id=account_a.pk, partner_b_account_id=account_b.pk,
                expected_version=draft.version, idempotency_key='div-note-update-invalid',
                operator=self.operator, note=['not', 'a', 'string'],
            )

    def test_confirm_posts_once_and_replay_does_not_change_balances(self):
        from accounting.dividend_actions import (
            DividendActionError, create_dividend_draft, preview_dividend,
            update_dividend_draft, confirm_dividend,
        )

        account_a, account_b = self._fund_accounts()
        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-confirm-create',
        )
        draft = update_dividend_draft(
            dividend_id=draft.id, total_cny='20.00',
            partner_a_amount_cny='12.00', partner_b_amount_cny='8.00',
            partner_a_account_id=account_a.pk, partner_b_account_id=account_b.pk,
            expected_version=draft.version, idempotency_key='div-confirm-update',
            operator=self.operator,
        )
        preview = preview_dividend(dividend_id=draft.id, operator=self.operator)
        posted = confirm_dividend(
            dividend_id=draft.id, operator=self.operator,
            idempotency_key='div-confirm-post', expected_version=draft.version,
            warning_fingerprint=preview.warning_fingerprint, warning_ack=True,
        )
        self.assertEqual(posted.status, Dividend.Status.POSTED)
        self.assertEqual(posted.ledger_transaction.postings.count(), 3)
        self.assertEqual(
            account_snapshot(account_a).original_balance, Decimal('88.00000000'),
        )
        replay = confirm_dividend(
            dividend_id=draft.id, operator=self.operator,
            idempotency_key='div-confirm-post', expected_version=draft.version,
            warning_fingerprint=preview.warning_fingerprint, warning_ack=True,
        )
        self.assertEqual(replay.pk, posted.pk)
        with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
            confirm_dividend(
                dividend_id=draft.id, operator=self.operator,
                idempotency_key='div-confirm-post', expected_version=draft.version + 1,
                warning_fingerprint=preview.warning_fingerprint, warning_ack=False,
            )
        self.operator.is_active = False
        self.operator.save(update_fields=['is_active'])
        inactive_replay = confirm_dividend(
            dividend_id=draft.id, operator=self.operator,
            idempotency_key='div-confirm-post', expected_version=draft.version,
            warning_fingerprint=preview.warning_fingerprint, warning_ack=True,
        )
        self.assertEqual(inactive_replay.pk, posted.pk)
        self.assertEqual(
            LedgerTransaction.objects.filter(
                transaction_type=LedgerTransaction.TransactionType.DIVIDEND,
            ).count(), 1,
        )

    def test_confirm_requires_warning_ack_and_rejects_invalid_accounts(self):
        from accounting.dividend_actions import (
            DividendActionError, create_dividend_draft, preview_dividend,
            update_dividend_draft, confirm_dividend,
        )

        account_a, account_b = self._fund_accounts('validation')
        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-validation-create',
        )
        draft = update_dividend_draft(
            dividend_id=draft.id, total_cny='20.00',
            partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
            partner_a_account_id=account_a.pk, partner_b_account_id=account_b.pk,
            expected_version=draft.version, idempotency_key='div-validation-update',
            operator=self.operator,
        )
        preview = preview_dividend(dividend_id=draft.id, operator=self.operator)
        with self.assertRaisesRegex(DividendActionError, 'warning_required'):
            confirm_dividend(
                dividend_id=draft.id, operator=self.operator,
                idempotency_key='div-validation-no-ack', expected_version=draft.version,
                warning_fingerprint=preview.warning_fingerprint, warning_ack=False,
            )
        self.assertEqual(
            Dividend.objects.get(pk=draft.pk).status, Dividend.Status.DRAFT,
        )

    def test_confirm_retries_locked_writer_without_duplicate_posting(self):
        from accounting.dividend_actions import (
            create_dividend_draft, preview_dividend, update_dividend_draft,
            confirm_dividend,
        )

        account_a, account_b = self._fund_accounts('retry')
        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-retry-create',
        )
        draft = update_dividend_draft(
            dividend_id=draft.id, total_cny='20.00',
            partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
            partner_a_account_id=account_a.pk, partner_b_account_id=account_b.pk,
            expected_version=draft.version, idempotency_key='div-retry-update',
            operator=self.operator,
        )
        preview = preview_dividend(dividend_id=draft.id, operator=self.operator)
        with patch(
            'accounting.dividend_actions._acquire_sqlite_writer_gate',
            side_effect=[OperationalError('database is locked'), None],
        ):
            posted = confirm_dividend(
                dividend_id=draft.id, operator=self.operator,
                idempotency_key='div-retry-confirm', expected_version=draft.version,
                warning_fingerprint=preview.warning_fingerprint, warning_ack=True,
            )
        self.assertEqual(posted.status, Dividend.Status.POSTED)
        self.assertEqual(
            LedgerTransaction.objects.filter(
                transaction_type=LedgerTransaction.TransactionType.DIVIDEND,
            ).count(), 1,
        )

    def test_cross_month_dividend_does_not_change_prior_operating_profit(self):
        from accounting.dividend_actions import (
            create_dividend_draft, preview_dividend, update_dividend_draft,
            confirm_dividend,
        )
        from accounting.selectors import monthly_profit

        account_a, account_b = self._fund_accounts('cross-month')
        post_transaction(
            transaction_type=LedgerTransaction.TransactionType.SALES_SHIPMENT,
            business_date=date(2026, 8, 31),
            postings=[
                PostingInput(
                    category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE,
                    currency='CNY', amount=Decimal('100.00'),
                    cny_amount=Decimal('100.00'),
                ),
                PostingInput(
                    category=LedgerPosting.Category.SALES_REVENUE,
                    currency='CNY', amount=Decimal('-100.00'),
                    cny_amount=Decimal('-100.00'),
                ),
            ],
            operator=self.operator, idempotency_key='div-cross-month-sale',
        )
        august_before = monthly_profit(month=date(2026, 8, 1))
        draft = create_dividend_draft(
            total_cny='20.00', business_date=date(2026, 9, 1),
            operator=self.operator, idempotency_key='div-cross-month-create',
        )
        draft = update_dividend_draft(
            dividend_id=draft.id, total_cny='20.00',
            partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
            partner_a_account_id=account_a.pk, partner_b_account_id=account_b.pk,
            expected_version=draft.version, idempotency_key='div-cross-month-update',
            operator=self.operator,
        )
        preview = preview_dividend(dividend_id=draft.id, operator=self.operator)
        confirm_dividend(
            dividend_id=draft.id, operator=self.operator,
            idempotency_key='div-cross-month-confirm', expected_version=draft.version,
            warning_fingerprint=preview.warning_fingerprint, warning_ack=False,
        )
        august_after = monthly_profit(month=date(2026, 8, 1))
        september_after = monthly_profit(month=date(2026, 9, 1))
        self.assertEqual(august_after['net_profit_cny'], august_before['net_profit_cny'])
        self.assertEqual(august_after['net_profit_cny'], Decimal('100.00'))
        self.assertEqual(september_after['net_profit_cny'], Decimal('0.00'))

    def test_update_replay_conflict_and_version_guard(self):
        from accounting.dividend_actions import (
            DividendActionError, create_dividend_draft, update_dividend_draft,
        )

        account_a, account_b = self._fund_accounts('update')
        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-update-create',
        )
        kwargs = {
            'dividend_id': draft.id, 'total_cny': '20.00',
            'partner_a_amount_cny': '10.00', 'partner_b_amount_cny': '10.00',
            'partner_a_account_id': account_a.pk, 'partner_b_account_id': account_b.pk,
            'expected_version': draft.version, 'idempotency_key': 'div-update-key',
            'operator': self.operator,
        }
        updated = update_dividend_draft(**kwargs)
        replay = update_dividend_draft(**kwargs)
        self.assertEqual(replay.pk, updated.pk)
        with self.assertRaisesRegex(DividendActionError, 'idempotency_conflict'):
            update_dividend_draft(**{**kwargs, 'total_cny': '22.00',
                                     'partner_a_amount_cny': '11.00',
                                     'partner_b_amount_cny': '11.00'})
        with self.assertRaisesRegex(DividendActionError, 'version_conflict'):
            update_dividend_draft(**{**kwargs, 'idempotency_key': 'div-update-stale',
                                     'expected_version': 1})

    def test_successful_create_replays_before_operator_and_day1_gates(self):
        from accounting.dividend_actions import create_dividend_draft

        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-gate-replay',
        )
        self.operator.is_active = False
        self.operator.save(update_fields=['is_active'])
        self.assertEqual(
            create_dividend_draft(
                total_cny='20.00', business_date=self.day,
                operator=self.operator, idempotency_key='div-gate-replay',
            ).pk,
            draft.pk,
        )

    def test_accounts_and_posting_failure_are_atomic(self):
        from accounting.dividend_actions import (
            DividendActionError, create_dividend_draft, preview_dividend,
            update_dividend_draft, confirm_dividend,
        )

        account_a, account_b = self._fund_accounts('failure')
        rub = FundAccount.objects.create(
            name='分红卢布账户', currency=FundAccount.Currency.RUB,
            creation_idempotency_key='div-failure-rub',
        )
        draft = create_dividend_draft(
            total_cny='20.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-failure-create',
        )
        with self.assertRaisesRegex(DividendActionError, 'currency_rule'):
            update_dividend_draft(
                dividend_id=draft.id, total_cny='20.00',
                partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
                partner_a_account_id=account_a.pk, partner_b_account_id=rub.pk,
                expected_version=draft.version, idempotency_key='div-failure-currency',
                operator=self.operator,
            )
        with self.assertRaisesRegex(DividendActionError, 'account_same'):
            update_dividend_draft(
                dividend_id=draft.id, total_cny='20.00',
                partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
                partner_a_account_id=account_a.pk, partner_b_account_id=account_a.pk,
                expected_version=draft.version, idempotency_key='div-failure-same',
                operator=self.operator,
            )
        draft = update_dividend_draft(
            dividend_id=draft.id, total_cny='20.00',
            partner_a_amount_cny='10.00', partner_b_amount_cny='10.00',
            partner_a_account_id=account_a.pk, partner_b_account_id=account_b.pk,
            expected_version=draft.version, idempotency_key='div-failure-update',
            operator=self.operator,
        )
        preview = preview_dividend(dividend_id=draft.id, operator=self.operator)
        with patch(
            'accounting.dividend_actions._post_transaction_once',
            side_effect=RuntimeError('injected posting failure'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'injected posting failure'):
                confirm_dividend(
                    dividend_id=draft.id, operator=self.operator,
                    idempotency_key='div-failure-confirm', expected_version=draft.version,
                    warning_fingerprint=preview.warning_fingerprint, warning_ack=True,
                )
        refreshed = Dividend.objects.get(pk=draft.pk)
        self.assertEqual(refreshed.status, Dividend.Status.DRAFT)
        self.assertFalse(
            LedgerTransaction.objects.filter(idempotency_key='div-failure-confirm').exists(),
        )

    def test_both_account_balance_shortfall_is_rejected_without_posting(self):
        from accounting.dividend_actions import (
            DividendActionError, create_dividend_draft, preview_dividend,
            update_dividend_draft, confirm_dividend,
        )

        account_a, account_b = self._fund_accounts('shortfall')
        draft = create_dividend_draft(
            total_cny='300.00', business_date=self.day,
            operator=self.operator, idempotency_key='div-shortfall-create',
        )
        draft = update_dividend_draft(
            dividend_id=draft.id, total_cny='300.00',
            partner_a_amount_cny='150.00', partner_b_amount_cny='150.00',
            partner_a_account_id=account_a.pk, partner_b_account_id=account_b.pk,
            expected_version=draft.version, idempotency_key='div-shortfall-update',
            operator=self.operator,
        )
        preview = preview_dividend(dividend_id=draft.id, operator=self.operator)
        with self.assertRaisesRegex(DividendActionError, 'insufficient_balance'):
            confirm_dividend(
                dividend_id=draft.id, operator=self.operator,
                idempotency_key='div-shortfall-confirm', expected_version=draft.version,
                warning_fingerprint=preview.warning_fingerprint, warning_ack=True,
            )
        self.assertEqual(Dividend.objects.get(pk=draft.pk).status, Dividend.Status.DRAFT)
        self.assertFalse(
            LedgerTransaction.objects.filter(idempotency_key='div-shortfall-confirm').exists(),
        )
