from decimal import Decimal
from datetime import date
import threading
from unittest.mock import patch

from django.db import close_old_connections
from django.conf import settings
from django.test import Client, TestCase, TransactionTestCase

from accounting import views as accounting_views
from accounting.models import Day1Initialization, FundAccount, LedgerTransaction
from accounting.selectors import account_snapshot
from accounting.services import record_opening_balance
from cigars.models import User


class AccountingApiPermissionTest(TestCase):
    def complete_day1(self, staff):
        return Day1Initialization.objects.create(
            singleton_key='company', status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10), completed_by=staff,
        )

    def test_accounts_rejects_authenticated_nonstaff_as_json(self):
        user = User.objects.create_user('api-partner', password='pass')
        self.client.force_login(user)

        response = self.client.get('/api/accounting/accounts/')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'error': '仅限工作人员访问', 'code': 'forbidden', 'details': {}})

    def test_staff_can_list_all_accounts_including_inactive(self):
        staff = User.objects.create_user('api-staff', password='pass', is_staff=True)
        second_staff = User.objects.create_user('api-staff-second', password='pass', is_staff=True)
        FundAccount.objects.create(
            name='API 人民币现金', currency='CNY', custodian=staff,
            creation_idempotency_key='api-list-cny',
        )
        inactive = FundAccount.objects.create(
            name='停用卢布账户', currency='RUB', is_active=False,
            creation_idempotency_key='api-list-rub',
        )
        self.client.force_login(staff)

        response = self.client.get('/api/accounting/accounts/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'accounts': [
            {
                'id': 1,
                'name': 'API 人民币现金',
                'currency': 'CNY',
                'custodian_id': staff.pk,
                'is_active': True,
            },
            {
                'id': inactive.pk,
                'name': '停用卢布账户',
                'currency': 'RUB',
                'custodian_id': None,
                'is_active': False,
            },
        ]})
        self.client.force_login(second_staff)
        self.assertEqual(self.client.get('/api/accounting/accounts/').json(), response.json())

    def test_staff_creates_account_and_reuses_matching_idempotency_key(self):
        staff = User.objects.create_user('api-account-staff', password='pass', is_staff=True)
        custodian = User.objects.create_user('api-custodian', password='pass', is_staff=True)
        self.client.force_login(staff)
        payload = {'name': '换汇 USDT 钱包', 'currency': 'USDT', 'custodian_id': custodian.pk}

        first = self.client.post(
            '/api/accounting/accounts/', data=payload, content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='create-usdt-wallet',
        )
        repeated = self.client.post(
            '/api/accounting/accounts/', data=payload, content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='create-usdt-wallet',
        )
        conflicting = self.client.post(
            '/api/accounting/accounts/', data={**payload, 'name': '另一钱包'},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='create-usdt-wallet',
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(first.json(), repeated.json())
        self.assertEqual(first.json()['account']['currency'], 'USDT')
        self.assertEqual(first.json()['account']['custodian_id'], custodian.pk)
        self.assertEqual(conflicting.status_code, 400)
        self.assertEqual(conflicting.json(), {'error': '幂等键已用于不同账户请求', 'code': 'input_error', 'details': {}})

    def test_staff_can_rename_and_deactivate_account_without_changing_currency(self):
        staff = User.objects.create_user('api-account-edit-staff', password='pass', is_staff=True)
        account = FundAccount.objects.create(
            name='待改名账户', currency='RUB', creation_idempotency_key='api-edit-account',
        )
        self.client.force_login(staff)

        renamed = self.client.patch(
            f'/api/accounting/accounts/{account.pk}/', data={'name': '卢布银行卡'},
            content_type='application/json',
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()['account']['name'], '卢布银行卡')
        self.assertEqual(renamed.json()['account']['currency'], 'RUB')

        disabled = self.client.patch(
            f'/api/accounting/accounts/{account.pk}/', data={'is_active': False},
            content_type='application/json',
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.json()['account']['is_active'])

        currency_change = self.client.patch(
            f'/api/accounting/accounts/{account.pk}/', data={'currency': 'CNY'},
            content_type='application/json',
        )
        self.assertEqual(currency_change.status_code, 400)
        self.assertEqual(currency_change.json()['error'], '账户币种不能修改')

    def test_opening_balance_returns_transaction_and_decimal_string_snapshot(self):
        staff = User.objects.create_user('api-opening-staff', password='pass', is_staff=True)
        account = FundAccount.objects.create(
            name='API 期初人民币', currency='CNY', creation_idempotency_key='api-opening-account',
        )
        self.client.force_login(staff)

        response = self.client.post(
            '/api/accounting/opening-balances/',
            data={
                'account_id': account.pk,
                'original_amount': '1200.00',
                'cny_book_cost': '1200.00',
                'equity_category': 'opening_capital',
                'business_date': '2026-08-10',
            },
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-opening-1',
        )

        self.assertEqual(response.status_code, 201)
        transaction = response.json()['transaction']
        self.assertIn('transaction_type', transaction)
        self.assertNotIn('type', transaction)
        self.assertEqual(transaction['transaction_type'], 'opening_balance')
        self.assertEqual(transaction['operator_id'], staff.pk)
        self.assertEqual(transaction['business_date'], '2026-08-10')
        self.assertEqual(transaction['effective_sequence'], 1)
        self.assertEqual(transaction['postings'][0]['amount'], '1200.00000000')
        self.assertEqual(response.json()['snapshots'], [{
            'id': account.pk,
            'name': 'API 期初人民币',
            'currency': 'CNY',
            'custodian_id': None,
            'is_active': True,
            'original_balance': '1200.00000000',
            'cny_book_cost': '1200.00',
            'moving_average_cny': '1',
        }])

    def test_exchange_moves_cny_and_usdt_into_rub_and_retry_does_not_change_balance(self):
        staff = User.objects.create_user('api-exchange-staff', password='pass', is_staff=True)
        self.complete_day1(staff)
        cny = FundAccount.objects.create(name='API 换汇人民币', currency='CNY', creation_idempotency_key='api-exchange-cny')
        usdt = FundAccount.objects.create(name='API 换汇 USDT', currency='USDT', creation_idempotency_key='api-exchange-usdt')
        rub = FundAccount.objects.create(name='API 换汇卢布', currency='RUB', creation_idempotency_key='api-exchange-rub')
        self.client.force_login(staff)
        for account, original_amount, cny_cost, key in (
            (cny, '100.00', '100.00', 'api-open-cny'),
            (usdt, '1.00000000', '50.00', 'api-open-usdt'),
        ):
            opening = self.client.post(
                '/api/accounting/opening-balances/',
                data={
                    'account_id': account.pk, 'original_amount': original_amount,
                    'cny_book_cost': cny_cost, 'equity_category': 'opening_capital',
                    'business_date': '2026-08-10',
                }, content_type='application/json', HTTP_IDEMPOTENCY_KEY=key,
            )
            self.assertEqual(opening.status_code, 201)

        cny_exchange = self.client.post(
            '/api/accounting/exchanges/',
            data={
                'source_account_id': cny.pk, 'rub_account_id': rub.pk,
                'source_amount': '100.00', 'rub_amount': '1200.00',
                'business_date': '2026-08-10', 'description': '人民币换汇',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-exchange-cny-rub',
        )
        usdt_exchange = self.client.post(
            '/api/accounting/exchanges/',
            data={
                'source_account_id': usdt.pk, 'rub_account_id': rub.pk,
                'source_amount': '1.00000000', 'rub_amount': '100.00',
                'business_date': '2026-08-10',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-exchange-usdt-rub',
        )
        retry = self.client.post(
            '/api/accounting/exchanges/',
            data={
                'source_account_id': cny.pk, 'rub_account_id': rub.pk,
                'source_amount': '100.00', 'rub_amount': '1200.00',
                'business_date': '2026-08-10', 'description': '人民币换汇',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-exchange-cny-rub',
        )

        self.assertEqual(cny_exchange.status_code, 201)
        self.assertEqual(usdt_exchange.status_code, 201)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(cny_exchange.json()['transaction']['id'], retry.json()['transaction']['id'])
        self.assertEqual(retry.json()['snapshots'][1]['original_balance'], '1300.00000000')
        self.assertEqual(retry.json()['snapshots'][1]['cny_book_cost'], '150.00')

    def test_exchange_api_has_day1_error_contract_and_replay(self):
        staff = User.objects.create_user('api-exchange-contract', password='pass', is_staff=True)
        cny = FundAccount.objects.create(name='换汇契约人民币', currency='CNY', creation_idempotency_key='exchange-contract-cny')
        rub = FundAccount.objects.create(name='换汇契约卢布', currency='RUB', creation_idempotency_key='exchange-contract-rub')
        self.client.force_login(staff)
        payload = {
            'source_account_id': cny.pk, 'rub_account_id': rub.pk,
            'source_amount': '1.00', 'rub_amount': '12.00', 'business_date': '2026-08-14',
        }
        blocked = self.client.post('/api/accounting/exchanges/', data=payload, content_type='application/json', HTTP_IDEMPOTENCY_KEY='exchange-contract-blocked')
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()['code'], 'day1_incomplete')
        self.assertIn('details', blocked.json())

        self.complete_day1(staff)
        record_opening_balance(cny, '10.00', '10.00', 'opening_capital', date(2026, 8, 10), staff, 'exchange-contract-opening')
        first = self.client.post('/api/accounting/exchanges/', data=payload, content_type='application/json', HTTP_IDEMPOTENCY_KEY='exchange-contract-replay')
        replay = self.client.post('/api/accounting/exchanges/', data=payload, content_type='application/json', HTTP_IDEMPOTENCY_KEY='exchange-contract-replay')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.json()['transaction']['id'], replay.json()['transaction']['id'])
        self.assertIsInstance(replay.json()['transaction']['postings'][0]['amount'], str)

    def test_exchange_api_maps_balance_and_currency_errors(self):
        staff = User.objects.create_user('api-exchange-errors', password='pass', is_staff=True)
        self.complete_day1(staff)
        cny = FundAccount.objects.create(name='错误人民币', currency='CNY', creation_idempotency_key='exchange-errors-cny')
        rub = FundAccount.objects.create(name='错误卢布', currency='RUB', creation_idempotency_key='exchange-errors-rub')
        rub_target = FundAccount.objects.create(name='错误第二卢布', currency='RUB', creation_idempotency_key='exchange-errors-rub-target')
        record_opening_balance(cny, '1.00', '1.00', 'opening_capital', date(2026, 8, 10), staff, 'exchange-errors-opening')
        self.client.force_login(staff)
        insufficient = self.client.post('/api/accounting/exchanges/', data={
            'source_account_id': cny.pk, 'rub_account_id': rub.pk, 'source_amount': '2.00', 'rub_amount': '24.00', 'business_date': '2026-08-14',
        }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='exchange-errors-insufficient')
        self.assertEqual(insufficient.status_code, 409)
        self.assertEqual(insufficient.json()['code'], 'insufficient_balance')
        currency = self.client.post('/api/accounting/exchanges/', data={
            'source_account_id': rub.pk, 'rub_account_id': rub_target.pk, 'source_amount': '1.00', 'rub_amount': '12.00', 'business_date': '2026-08-14',
        }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='exchange-errors-currency')
        self.assertEqual(currency.status_code, 400)
        self.assertEqual(currency.json()['code'], 'currency_rule')

    def test_same_currency_transfer_moves_exact_cost_between_accounts(self):
        staff = User.objects.create_user('api-transfer-staff', password='pass', is_staff=True)
        self.complete_day1(staff)
        source = FundAccount.objects.create(name='API 转账源', currency='RUB', creation_idempotency_key='api-transfer-source')
        target = FundAccount.objects.create(name='API 转账目标', currency='RUB', creation_idempotency_key='api-transfer-target')
        self.client.force_login(staff)
        opening = self.client.post(
            '/api/accounting/opening-balances/',
            data={
                'account_id': source.pk, 'original_amount': '1200.00', 'cny_book_cost': '100.00',
                'equity_category': 'opening_capital', 'business_date': '2026-08-10',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-transfer-opening',
        )
        self.assertEqual(opening.status_code, 201)

        response = self.client.post(
            '/api/accounting/transfers/',
            data={
                'source_account_id': source.pk, 'target_account_id': target.pk,
                'amount': '600.00', 'business_date': '2026-08-10', 'description': '调拨',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-transfer-1',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['transaction']['transaction_type'], 'transfer')
        self.assertEqual(response.json()['snapshots'], [
            {
                'id': source.pk, 'name': 'API 转账源', 'currency': 'RUB',
                'custodian_id': None, 'is_active': True, 'original_balance': '600.00000000',
                'cny_book_cost': '50.00', 'moving_average_cny': str(Decimal('50') / Decimal('600')),
            },
            {
                'id': target.pk, 'name': 'API 转账目标', 'currency': 'RUB',
                'custodian_id': None, 'is_active': True, 'original_balance': '600.00000000',
                'cny_book_cost': '50.00', 'moving_average_cny': str(Decimal('50') / Decimal('600')),
            },
        ])

    def test_overview_returns_active_account_snapshots_with_strings_and_null_average(self):
        staff = User.objects.create_user('api-overview-staff', password='pass', is_staff=True)
        cny = FundAccount.objects.create(name='API 总览人民币', currency='CNY', creation_idempotency_key='api-overview-cny')
        empty_usdt = FundAccount.objects.create(name='API 总览空 USDT', currency='USDT', creation_idempotency_key='api-overview-usdt')
        FundAccount.objects.create(
            name='API 总览停用账户', currency='RUB', is_active=False,
            creation_idempotency_key='api-overview-inactive',
        )
        self.client.force_login(staff)
        opening = self.client.post(
            '/api/accounting/opening-balances/',
            data={
                'account_id': cny.pk, 'original_amount': '100.00', 'cny_book_cost': '100.00',
                'equity_category': 'opening_capital', 'business_date': '2026-08-10',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-overview-opening',
        )
        self.assertEqual(opening.status_code, 201)

        response = self.client.get('/api/accounting/overview/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['accounts'], [
            {
                'id': cny.pk, 'name': 'API 总览人民币', 'currency': 'CNY',
                'custodian_id': None, 'is_active': True,
                'original_balance': '100.00000000', 'cny_book_cost': '100.00',
                'moving_average_cny': '1',
            },
            {
                'id': empty_usdt.pk, 'name': 'API 总览空 USDT', 'currency': 'USDT',
                'custodian_id': None, 'is_active': True,
                'original_balance': '0.00000000', 'cny_book_cost': '0.00', 'moving_average_cny': None,
            },
        ])

    def test_transactions_are_stable_with_postings_and_account_date_filters(self):
        staff = User.objects.create_user('api-transactions-staff', password='pass', is_staff=True)
        self.complete_day1(staff)
        cny = FundAccount.objects.create(name='API 流水人民币', currency='CNY', creation_idempotency_key='api-transactions-cny')
        rub = FundAccount.objects.create(name='API 流水卢布', currency='RUB', creation_idempotency_key='api-transactions-rub')
        self.client.force_login(staff)
        opening = self.client.post(
            '/api/accounting/opening-balances/',
            data={
                'account_id': cny.pk, 'original_amount': '100.00', 'cny_book_cost': '100.00',
                'equity_category': 'opening_capital', 'business_date': '2026-08-10',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-transactions-opening',
        )
        self.assertEqual(opening.status_code, 201)
        exchange = self.client.post(
            '/api/accounting/exchanges/',
            data={
                'source_account_id': cny.pk, 'rub_account_id': rub.pk,
                'source_amount': '100.00', 'rub_amount': '1200.00', 'business_date': '2026-08-10',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-transactions-exchange',
        )
        self.assertEqual(exchange.status_code, 201)

        response = self.client.get('/api/accounting/transactions/')
        account_filtered = self.client.get(f'/api/accounting/transactions/?account_id={rub.pk}')
        date_filtered = self.client.get('/api/accounting/transactions/?business_date_from=2026-08-10&business_date_to=2026-08-10')
        invalid_filter = self.client.get('/api/accounting/transactions/?account_id=not-an-id')
        exchange_filtered = self.client.get('/api/accounting/transactions/?transaction_type=exchange')
        invalid_type = self.client.get('/api/accounting/transactions/?transaction_type=not-a-transaction')
        inverted_dates = self.client.get('/api/accounting/transactions/?business_date_from=2026-08-11&business_date_to=2026-08-10')
        limited = self.client.get('/api/accounting/transactions/?limit=1')
        invalid_limit = self.client.get('/api/accounting/transactions/?limit=0')
        excessive_limit = self.client.get('/api/accounting/transactions/?limit=501')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['transaction_type'] for item in response.json()['transactions']],
            ['opening_balance', 'exchange'],
        )
        self.assertEqual(response.json()['transactions'][1]['postings'], [
            {'account_id': cny.pk, 'category': '', 'currency': 'CNY', 'amount': '-100.00000000', 'cny_amount': '-100.00'},
            {'account_id': rub.pk, 'category': '', 'currency': 'RUB', 'amount': '1200.00000000', 'cny_amount': '100.00'},
        ])
        self.assertEqual(
            [item['transaction_type'] for item in account_filtered.json()['transactions']],
            ['exchange'],
        )
        self.assertEqual(date_filtered.json(), response.json())
        self.assertEqual(invalid_filter.status_code, 400)
        self.assertEqual([item['transaction_type'] for item in exchange_filtered.json()['transactions']], ['exchange'])
        self.assertEqual(invalid_type.status_code, 400)
        self.assertEqual(inverted_dates.status_code, 400)
        self.assertEqual(len(limited.json()['transactions']), 1)
        self.assertEqual(invalid_limit.status_code, 400)
        self.assertEqual(excessive_limit.status_code, 400)

    def test_all_endpoints_reject_anonymous_and_authenticated_nonstaff_as_json(self):
        endpoints = [
            ('get', '/api/accounting/accounts/'),
            ('post', '/api/accounting/accounts/'),
            ('post', '/api/accounting/opening-balances/'),
            ('post', '/api/accounting/exchanges/'),
            ('post', '/api/accounting/transfers/'),
            ('get', '/api/accounting/overview/'),
            ('get', '/api/accounting/transactions/'),
        ]
        nonstaff = User.objects.create_user('api-no-access', password='pass')
        for actor, user in (('anonymous', None), ('nonstaff', nonstaff)):
            self.client.logout()
            if user is not None:
                self.client.force_login(user)
            for method, path in endpoints:
                with self.subTest(actor=actor, path=path):
                    response = getattr(self.client, method)(
                        path, data={}, content_type='application/json', HTTP_IDEMPOTENCY_KEY='permission-key',
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json(), {'error': '仅限工作人员访问', 'code': 'forbidden', 'details': {}})

    def test_telegram_staff_header_is_not_accounting_authentication(self):
        User.objects.create_user(
            'api-telegram-staff', password='pass', is_staff=True, telegram_id='api-telegram-42',
        )

        response = self.client.get('/api/accounting/accounts/', HTTP_X_TELEGRAM_ID='api-telegram-42')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'error': '仅限工作人员访问', 'code': 'forbidden', 'details': {}})

    def test_staff_writes_require_csrf_token(self):
        staff = User.objects.create_user('api-csrf-staff', password='pass', is_staff=True)
        client = Client(enforce_csrf_checks=True)
        client.force_login(staff)
        payload = {'name': 'CSRF 账户', 'currency': 'CNY'}

        for path in (
            '/api/accounting/accounts/',
            '/api/accounting/opening-balances/',
            '/api/accounting/exchanges/',
            '/api/accounting/transfers/',
        ):
            with self.subTest(path=path):
                missing_token = client.post(
                    path, data=payload, content_type='application/json',
                    HTTP_IDEMPOTENCY_KEY=f'csrf-{path}',
                )
                self.assertEqual(missing_token.status_code, 403)
        token = 'a' * 32
        client.cookies[settings.CSRF_COOKIE_NAME] = token
        valid_token = client.post(
            '/api/accounting/accounts/', data=payload, content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='csrf-account-valid', HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(valid_token.status_code, 201)

    def test_writes_require_application_json_content_type(self):
        staff = User.objects.create_user('api-content-type-staff', password='pass', is_staff=True)
        self.client.force_login(staff)

        response = self.client.post(
            '/api/accounting/accounts/', data='{"name":"错误媒体类型","currency":"CNY"}',
            content_type='text/plain', HTTP_IDEMPOTENCY_KEY='text-plain-account',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': '请求体必须是 JSON 对象', 'code': 'input_error', 'details': {}})
        self.assertEqual(FundAccount.objects.count(), 0)

    def test_float_account_id_is_rejected_without_using_integer_account(self):
        staff = User.objects.create_user('api-id-staff', password='pass', is_staff=True)
        account = FundAccount.objects.create(
            name='整数账户', currency='CNY', creation_idempotency_key='integer-account',
        )
        self.client.force_login(staff)

        response = self.client.post(
            '/api/accounting/opening-balances/',
            data={
                'account_id': float(account.pk) + 0.5,
                'original_amount': '100.00', 'cny_book_cost': '100.00',
                'equity_category': 'opening_capital', 'business_date': '2026-08-10',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='float-account-id',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_infinite_ids_are_rejected_and_numeric_string_custodian_is_supported(self):
        staff = User.objects.create_user('api-infinite-id-staff', password='pass', is_staff=True)
        account = FundAccount.objects.create(
            name='Infinity 账户', currency='CNY', creation_idempotency_key='infinity-account',
        )
        self.client.force_login(staff)
        invalid_account = self.client.post(
            '/api/accounting/opening-balances/',
            data={
                'account_id': float('inf'),
                'original_amount': '100.00', 'cny_book_cost': '100.00',
                'equity_category': 'opening_capital', 'business_date': '2026-08-10',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='infinite-account-id',
        )
        invalid_custodian = self.client.post(
            '/api/accounting/accounts/',
            data={'name': 'Infinity 保管人', 'currency': 'CNY', 'custodian_id': float('inf')},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='infinite-custodian-id',
        )
        string_custodian = self.client.post(
            '/api/accounting/accounts/',
            data={'name': '字符串保管人', 'currency': 'CNY', 'custodian_id': str(staff.pk)},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='string-custodian-id',
        )

        self.assertEqual(invalid_account.status_code, 400)
        self.assertEqual(invalid_custodian.status_code, 400)
        self.assertEqual(string_custodian.status_code, 201)
        self.assertEqual(string_custodian.json()['account']['custodian_id'], staff.pk)
        self.assertEqual(LedgerTransaction.objects.count(), 0)

    def test_writes_reject_invalid_json_or_missing_key_and_account_errors_as_json_400(self):
        staff = User.objects.create_user('api-input-staff', password='pass', is_staff=True)
        self.client.force_login(staff)
        write_paths = [
            '/api/accounting/accounts/', '/api/accounting/opening-balances/',
            '/api/accounting/exchanges/', '/api/accounting/transfers/',
        ]
        for path in write_paths:
            with self.subTest(path=path):
                response = self.client.post(
                    path, data='[]', content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-invalid-json',
                )
                self.assertEqual(response.status_code, 400)
                expected = {'error': '请求体必须是 JSON 对象', 'code': 'input_error', 'details': {}}
                self.assertEqual(response.json(), expected)

        missing_key = self.client.post(
            '/api/accounting/accounts/', data={'name': '无键账户', 'currency': 'CNY'}, content_type='application/json',
        )
        long_key = self.client.post(
            '/api/accounting/accounts/', data={'name': '长键账户', 'currency': 'CNY'},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='x' * 129,
        )
        invalid_currency = self.client.post(
            '/api/accounting/accounts/', data={'name': '无效币种', 'currency': 'EUR'},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-invalid-currency',
        )
        unknown_custodian = self.client.post(
            '/api/accounting/accounts/', data={'name': '未知保管人', 'currency': 'CNY', 'custodian_id': 999999},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-unknown-custodian',
        )
        first = self.client.post(
            '/api/accounting/accounts/', data={'name': '重名账户', 'currency': 'CNY'},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-name-one',
        )
        duplicate_name = self.client.post(
            '/api/accounting/accounts/', data={'name': '重名账户', 'currency': 'CNY'},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-name-two',
        )

        self.assertEqual(missing_key.status_code, 400)
        self.assertEqual(long_key.status_code, 400)
        self.assertEqual(invalid_currency.status_code, 400)
        self.assertEqual(unknown_custodian.status_code, 400)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate_name.status_code, 400)


class AccountingApiConcurrencyTest(TransactionTestCase):
    business_date = '2026-08-10'

    def test_concurrent_same_key_exchange_returns_created_and_replayed_statuses_once(self):
        operator = User.objects.create_user(
            'api-concurrent-operator', password='pass', is_staff=True, telegram_id='api-concurrent-telegram',
        )
        Day1Initialization.objects.create(
            singleton_key='company', status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10), completed_by=operator,
        )
        cny = FundAccount.objects.create(
            name='API 并发人民币', currency='CNY', creation_idempotency_key='api-concurrent-cny',
        )
        rub = FundAccount.objects.create(
            name='API 并发卢布', currency='RUB', creation_idempotency_key='api-concurrent-rub',
        )
        record_opening_balance(
            cny, '100.00', '100.00', 'opening_capital',
            date(2026, 8, 10), operator, 'api-concurrent-opening',
        )
        authenticated_client = Client()
        authenticated_client.force_login(operator)
        session_cookie = authenticated_client.cookies[settings.SESSION_COOKIE_NAME].value
        entered_service = threading.Barrier(2)
        responses = []
        errors = []
        payload = {
            'source_account_id': cny.pk,
            'rub_account_id': rub.pk,
            'source_amount': '100.00',
            'rub_amount': '1200.00',
            'business_date': self.business_date,
        }
        original_exchange = accounting_views._exchange_to_rub_with_result

        def synchronize_after_exists(*args, **kwargs):
            entered_service.wait(timeout=10)
            return original_exchange(*args, **kwargs)

        def submit():
            close_old_connections()
            try:
                client = Client()
                client.cookies[settings.SESSION_COOKIE_NAME] = session_cookie
                response = client.post(
                    '/api/accounting/exchanges/', data=payload, content_type='application/json',
                    HTTP_IDEMPOTENCY_KEY='api-concurrent-exchange',
                )
                responses.append(response)
            except Exception as error:
                errors.append(error)
            finally:
                close_old_connections()

        with patch('accounting.views._exchange_to_rub_with_result', side_effect=synchronize_after_exists):
            threads = [threading.Thread(target=submit) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(response.status_code for response in responses), [200, 201])
        exchanges = list(LedgerTransaction.objects.filter(transaction_type='exchange'))
        self.assertEqual(len(exchanges), 1)
        self.assertEqual(exchanges[0].postings.count(), 2)
        self.assertEqual(account_snapshot(rub).original_balance, Decimal('1200.00000000'))
