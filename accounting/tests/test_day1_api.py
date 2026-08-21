from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase

from accounting.business_time import moscow_business_date
from accounting.models import (
    AccountReconciliation, Day1Initialization, FundAccount, LedgerPosting,
    LedgerTransaction,
)
from accounting.services import PostingInput, post_transaction
from accounting.services import create_reconciliation
from cigars.models import Cigar, PurchaseBatch, User


class Day1ApiTest(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            'day1-api-staff', password='pass', is_staff=True,
        )
        self.nonstaff = User.objects.create_user(
            'day1-api-nonstaff', password='pass',
        )
        self.cigar = Cigar.objects.create(
            brand='Day 1 API Brand',
            english_name='Day 1 API Cigar',
            name='期初接口雪茄',
        )

    def payload(self):
        return {
            'business_date': max(moscow_business_date(), date(2026, 8, 10)).isoformat(),
            'accounts': [
                {
                    'slot': 'owner_cny', 'name': '我的人民币',
                    'currency': 'CNY', 'original_amount': '100.00',
                    'cny_book_cost': '100.00',
                },
                {
                    'slot': 'partner_cny', 'name': '合伙人人民币',
                    'currency': 'CNY', 'original_amount': '0.00',
                    'cny_book_cost': '0.00',
                },
                {
                    'slot': 'rub', 'name': '卢布银行卡',
                    'currency': 'RUB', 'original_amount': '1200.00',
                    'cny_book_cost': '100.00',
                },
                {
                    'slot': 'usdt', 'name': 'USDT 账户',
                    'currency': 'USDT', 'original_amount': '10.00000000',
                    'cny_book_cost': '70.00',
                },
            ],
            'inventory': [
                {
                    'cigar_id': self.cigar.pk, 'box_size': 25,
                    'box_quantity': 1, 'loose_sticks': 2,
                    'unit_cost_cny': '12.50',
                },
            ],
        }

    def save_draft(self, *, version='0'):
        return self.client.put(
            '/api/accounting/day1/draft/',
            data=self.payload(),
            content_type='application/json',
            HTTP_IF_MATCH=version,
        )

    def confirm(self, *, version=1, key='day1-api-confirm'):
        return self.client.post(
            '/api/accounting/day1/confirm/',
            data={'version': version},
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_status_draft_save_and_confirm_contract(self):
        self.client.force_login(self.staff)

        not_started = self.client.get('/api/accounting/day1/')
        saved = self.save_draft()
        draft = self.client.get('/api/accounting/day1/')
        confirmed = self.confirm()
        completed = self.client.get('/api/accounting/day1/')

        self.assertEqual(not_started.status_code, 200)
        self.assertEqual(not_started.json(), {
            'status': 'not_started',
            'version': 0,
            'business_date': None,
            'draft': None,
            'completion_summary': None,
        })
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['status'], 'draft')
        self.assertEqual(saved.json()['version'], 1)
        accounts = {
            row['slot']: row
            for row in saved.json()['draft']['accounts']
        }
        self.assertEqual(accounts['owner_cny']['original_amount'], '100.00')
        self.assertEqual(accounts['partner_cny']['original_amount'], '0.00')
        self.assertEqual(accounts['rub']['original_amount'], '1200.00')
        self.assertEqual(accounts['usdt']['original_amount'], '10.00000000')
        self.assertEqual(saved.json()['draft']['inventory'][0]['unit_cost_cny'], '12.50')
        self.assertEqual(draft.json(), saved.json())
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()['status'], 'completed')
        self.assertEqual(confirmed.json()['version'], 1)
        self.assertEqual(
            confirmed.json()['completion_summary']['opening_capital_cny'],
            '607.50',
        )
        self.assertIsNone(completed.json()['draft'])
        self.assertEqual(
            completed.json()['completion_summary'],
            confirmed.json()['completion_summary'],
        )
        self.assertEqual(FundAccount.objects.count(), 4)
        self.assertEqual(
            PurchaseBatch.objects.filter(source=PurchaseBatch.Source.OPENING).count(),
            1,
        )

    def test_draft_requires_if_match_but_accepts_incomplete_fields(self):
        self.client.force_login(self.staff)

        missing = self.client.put(
            '/api/accounting/day1/draft/',
            data=self.payload(),
            content_type='application/json',
        )
        incomplete = self.payload()
        incomplete['accounts'][0]['original_amount'] = ''
        incomplete['accounts'][0]['cny_book_cost'] = ''
        incomplete_response = self.client.put(
            '/api/accounting/day1/draft/',
            data=incomplete,
            content_type='application/json',
            HTTP_IF_MATCH='0',
        )
        stale = self.save_draft(version='0')

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()['error'], 'If-Match 版本不能为空')
        self.assertEqual(incomplete_response.status_code, 200)
        self.assertEqual(
            incomplete_response.json()['draft']['accounts'][0]['original_amount'],
            '',
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()['code'], 'version_conflict')

        huge_version = self.save_draft(version='9' * 5000)
        self.assertEqual(huge_version.status_code, 400)
        self.assertEqual(huge_version.json()['code'], 'input_error')

    def test_confirm_requires_idempotency_key_and_replays_frozen_summary(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.save_draft().status_code, 200)

        missing_key = self.client.post(
            '/api/accounting/day1/confirm/',
            data={'version': 1},
            content_type='application/json',
        )
        first = self.confirm()
        replay = self.confirm()
        different = self.confirm(key='day1-api-different')

        self.assertEqual(missing_key.status_code, 400)
        self.assertEqual(missing_key.json()['error'], '幂等键不能为空')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(different.status_code, 200)
        self.assertEqual(different.json(), first.json())

    def test_day1_and_dashboard_endpoints_are_staff_only(self):
        endpoints = (
            ('get', '/api/accounting/day1/'),
            ('put', '/api/accounting/day1/draft/'),
            ('post', '/api/accounting/day1/confirm/'),
            ('get', '/api/accounting/dashboard/'),
        )
        for actor, user in (('anonymous', None), ('nonstaff', self.nonstaff)):
            self.client.logout()
            if user is not None:
                self.client.force_login(user)
            for method, path in endpoints:
                with self.subTest(actor=actor, path=path):
                    response = getattr(self.client, method)(
                        path,
                        data=self.payload(),
                        content_type='application/json',
                        HTTP_IF_MATCH='0',
                        HTTP_IDEMPOTENCY_KEY='permission-test',
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json(), {'error': '仅限工作人员访问', 'code': 'forbidden', 'details': {}})

    def test_dashboard_does_not_render_unknown_opening_values_as_zero(self):
        self.client.force_login(self.staff)

        response = self.client.get('/api/accounting/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['requires_day1'])
        self.assertEqual(response.json()['day1_status'], 'not_started')
        self.assertEqual(response.json()['stats'], {
            'total_funds_cny': None,
            'cny_funds_total': None,
            'inventory_book_cost_cny': None,
            'accounts_receivable_cny': None,
            'month_net_profit_cny': None,
        })
        self.assertEqual(response.json()['accounts'], [])
        self.assertIsNone(response.json()['monthly_profit'])

    def test_dashboard_returns_initialized_assets_profit_and_reconciliation_state(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.save_draft().status_code, 200)
        self.assertEqual(self.confirm().status_code, 200)

        response = self.client.get('/api/accounting/dashboard/')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['requires_day1'])
        self.assertEqual(data['day1_status'], 'completed')
        self.assertEqual(data['stats'], {
            'total_funds_cny': '607.50',
            'cny_funds_total': '100.00',
            'inventory_book_cost_cny': '337.50',
            'accounts_receivable_cny': '0.00',
            'month_net_profit_cny': '0.00',
        })
        self.assertEqual(len(data['accounts']), 4)
        self.assertEqual(data['monthly_profit']['net_profit_cny'], '0.00')
        self.assertEqual(data['reconciliation']['pending_count'], 0)
        self.assertEqual(data['reconciliation']['latest'], [])

    def test_dashboard_total_funds_keeps_inactive_account_balance(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.save_draft().status_code, 200)
        self.assertEqual(self.confirm().status_code, 200)
        FundAccount.objects.filter(currency='USDT').update(is_active=False)

        response = self.client.get('/api/accounting/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['stats']['total_funds_cny'], '607.50')
        self.assertEqual(len(response.json()['accounts']), 3)

    def test_dashboard_excludes_future_reconciliations(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.save_draft().status_code, 200)
        self.assertEqual(self.confirm().status_code, 200)
        account = FundAccount.objects.filter(currency='CNY').first()
        future = moscow_business_date() + timedelta(days=1)
        create_reconciliation(
            account=account,
            business_date=future,
            actual_amount='100.00',
            operator=self.staff,
            idempotency_key='future-reconciliation',
        )

        response = self.client.get('/api/accounting/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['reconciliation']['pending_count'], 0)
        self.assertEqual(response.json()['reconciliation']['latest'], [])

    def test_dashboard_uses_posted_receivable_and_profit_facts(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.save_draft().status_code, 200)
        self.assertEqual(self.confirm().status_code, 200)
        business_date = moscow_business_date()
        post_transaction(
            transaction_type=LedgerTransaction.TransactionType.SALES_SHIPMENT,
            business_date=business_date,
            postings=[
                PostingInput(
                    category=LedgerPosting.Category.ACCOUNTS_RECEIVABLE,
                    currency='CNY', amount=Decimal('50.00'),
                    cny_amount=Decimal('50.00'),
                ),
                PostingInput(
                    category=LedgerPosting.Category.SALES_REVENUE,
                    currency='CNY', amount=Decimal('-50.00'),
                    cny_amount=Decimal('-50.00'),
                ),
            ],
            operator=self.staff,
            idempotency_key='day1-dashboard-sale',
        )

        response = self.client.get('/api/accounting/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['stats']['accounts_receivable_cny'], '50.00')
        self.assertEqual(response.json()['stats']['month_net_profit_cny'], '50.00')

    def test_dashboard_does_not_query_snapshots_per_account(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.save_draft().status_code, 200)
        self.assertEqual(self.confirm().status_code, 200)
        from accounting import selectors
        original = selectors.account_snapshot

        with patch(
            'accounting.selectors.account_snapshot',
            wraps=original,
        ) as snapshot:
            response = self.client.get('/api/accounting/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(snapshot.call_count, 0)

    def test_day1_write_endpoints_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        for method, path in (
            ('put', '/api/accounting/day1/draft/'),
            ('post', '/api/accounting/day1/confirm/'),
        ):
            with self.subTest(path=path):
                response = getattr(client, method)(
                    path,
                    data=self.payload() if method == 'put' else {'version': 1},
                    content_type='application/json',
                    HTTP_IF_MATCH='0',
                    HTTP_IDEMPOTENCY_KEY='day1-csrf',
                )
                self.assertEqual(response.status_code, 403)

        token = 'a' * 32
        client.cookies[settings.CSRF_COOKIE_NAME] = token
        saved = client.put(
            '/api/accounting/day1/draft/',
            data=self.payload(),
            content_type='application/json',
            HTTP_IF_MATCH='0',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(saved.status_code, 200)

    def test_dashboard_uses_moscow_business_date_across_shanghai_midnight(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.save_draft().status_code, 200)
        self.assertEqual(self.confirm().status_code, 200)
        # 16:30 UTC is already the next day in Shanghai, but still today in Moscow.
        instant = datetime(2026, 8, 31, 16, 30, tzinfo=datetime_timezone.utc)
        from accounting.business_time import moscow_business_date
        self.assertEqual(moscow_business_date(instant), date(2026, 8, 31))

        with patch(
            'accounting.views.moscow_business_date',
            return_value=moscow_business_date(instant),
        ):
            response = self.client.get('/api/accounting/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['monthly_profit']['period_start'], '2026-08-01')

    def test_completed_initialization_cannot_be_replaced_through_draft_api(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.save_draft().status_code, 200)
        self.assertEqual(self.confirm().status_code, 200)

        response = self.save_draft(version='1')

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'day1_conflict')
        self.assertEqual(Day1Initialization.objects.get().status, 'completed')
