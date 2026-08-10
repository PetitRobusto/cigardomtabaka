from decimal import Decimal

from django.test import TestCase

from accounting.models import FundAccount
from cigars.models import User


class AccountingApiPermissionTest(TestCase):
    def test_accounts_rejects_authenticated_nonstaff_as_json(self):
        user = User.objects.create_user('api-partner', password='pass')
        self.client.force_login(user)

        response = self.client.get('/api/accounting/accounts/')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'error': '仅限工作人员访问'})

    def test_staff_can_list_active_accounts(self):
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
        self.assertEqual(response.json(), {
            'accounts': [{
                'id': 1,
                'name': 'API 人民币现金',
                'currency': 'CNY',
                'custodian_id': staff.pk,
                'is_active': True,
            }],
        })
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
        self.assertEqual(conflicting.json(), {'error': '幂等键已用于不同账户请求'})

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
        self.assertEqual(response.json()['transaction']['type'], 'opening_balance')
        self.assertEqual(response.json()['transaction']['operator_id'], staff.pk)
        self.assertEqual(response.json()['transaction']['date'], '2026-08-10')
        self.assertEqual(response.json()['transaction']['postings'][0]['amount'], '1200.00000000')
        self.assertEqual(response.json()['snapshots'], [{
            'account_id': account.pk,
            'currency': 'CNY',
            'original_balance': '1200.00000000',
            'cny_book_cost': '1200.00',
            'moving_average_cny': '1',
        }])

    def test_exchange_moves_cny_and_usdt_into_rub_and_retry_does_not_change_balance(self):
        staff = User.objects.create_user('api-exchange-staff', password='pass', is_staff=True)
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

    def test_same_currency_transfer_moves_exact_cost_between_accounts(self):
        staff = User.objects.create_user('api-transfer-staff', password='pass', is_staff=True)
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
        self.assertEqual(response.json()['transaction']['type'], 'transfer')
        self.assertEqual(response.json()['snapshots'], [
            {
                'account_id': source.pk, 'currency': 'RUB', 'original_balance': '600.00000000',
                'cny_book_cost': '50.00', 'moving_average_cny': str(Decimal('50') / Decimal('600')),
            },
            {
                'account_id': target.pk, 'currency': 'RUB', 'original_balance': '600.00000000',
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
                'snapshot': {
                    'account_id': cny.pk, 'currency': 'CNY',
                    'original_balance': '100.00000000', 'cny_book_cost': '100.00',
                    'moving_average_cny': '1',
                },
            },
            {
                'id': empty_usdt.pk, 'name': 'API 总览空 USDT', 'currency': 'USDT',
                'custodian_id': None, 'is_active': True,
                'snapshot': {
                    'account_id': empty_usdt.pk, 'currency': 'USDT',
                    'original_balance': '0.00000000', 'cny_book_cost': '0.00', 'moving_average_cny': None,
                },
            },
        ])

    def test_transactions_are_stable_with_postings_and_account_date_filters(self):
        staff = User.objects.create_user('api-transactions-staff', password='pass', is_staff=True)
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
        inverted_dates = self.client.get('/api/accounting/transactions/?business_date_from=2026-08-11&business_date_to=2026-08-10')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['type'] for item in response.json()['transactions']], ['opening_balance', 'exchange'])
        self.assertEqual(response.json()['transactions'][1]['postings'], [
            {'account_id': cny.pk, 'category': '', 'currency': 'CNY', 'amount': '-100.00000000', 'cny_amount': '-100.00'},
            {'account_id': rub.pk, 'category': '', 'currency': 'RUB', 'amount': '1200.00000000', 'cny_amount': '100.00'},
        ])
        self.assertEqual([item['type'] for item in account_filtered.json()['transactions']], ['exchange'])
        self.assertEqual(date_filtered.json(), response.json())
        self.assertEqual(invalid_filter.status_code, 400)
        self.assertEqual(inverted_dates.status_code, 400)

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
                    self.assertEqual(response.json(), {'error': '仅限工作人员访问'})

    def test_telegram_staff_header_resolves_real_operator_for_write(self):
        staff = User.objects.create_user(
            'api-telegram-staff', password='pass', is_staff=True, telegram_id='api-telegram-42',
        )
        account = FundAccount.objects.create(
            name='API Telegram 账户', currency='CNY', creation_idempotency_key='api-telegram-account',
        )

        response = self.client.post(
            '/api/accounting/opening-balances/',
            data={
                'account_id': account.pk, 'original_amount': '1.00', 'cny_book_cost': '1.00',
                'equity_category': 'opening_capital', 'business_date': '2026-08-10',
            }, content_type='application/json', HTTP_IDEMPOTENCY_KEY='api-telegram-opening',
            HTTP_X_TELEGRAM_ID='api-telegram-42',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['transaction']['operator_id'], staff.pk)

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
                self.assertEqual(response.json(), {'error': '请求体必须是 JSON 对象'})

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
