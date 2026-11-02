from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounting.models import FundAccount
from cigars.models import SalesOrder, User
from privnote.models import PaymentSubmission, Privnote


class SalesPaginationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('pagination-staff', is_staff=True)
        cls.orders = SalesOrder.objects.bulk_create([
            SalesOrder(customer_name='分页客户', operator=cls.staff) for _ in range(41)
        ])
        # 相同创建时刻也必须有稳定的页边界。
        SalesOrder.objects.update(created_at=timezone.now())

    def setUp(self):
        self.client.force_login(self.staff)

    def test_default_twenty_and_all_pages_without_duplicates(self):
        seen = []
        for page, size in [(1, 20), (2, 20), (3, 1)]:
            response = self.client.get('/api/sales/orders/', {'page': page})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual((data['count'], data['page'], data['pages'], data['limit']), (41, page, 3, 20))
            self.assertEqual(len(data['results']), size)
            seen.extend(row['id'] for row in data['results'])
        self.assertEqual(seen, sorted([order.id for order in self.orders], reverse=True))

    def test_out_of_range_and_empty_results(self):
        last = self.client.get('/api/sales/orders/', {'page': 999, 'limit': 20}).json()
        self.assertEqual((last['page'], len(last['results'])), (3, 1))
        empty = self.client.get('/api/sales/orders/', {'page': 999, 'q': '不存在'}).json()
        self.assertEqual((empty['count'], empty['page'], empty['pages'], empty['results']), (0, 1, 1, []))

    def test_invalid_pagination_is_rejected(self):
        for params in [{'page': value} for value in ['0', '-1', '1.5', 'abc', '2147483648']] + [
            {'limit': '0'}, {'limit': '101'}, {'limit': 'bad'}, {'review_only': 'yes'}, {'recent_only': 'yes'},
        ]:
            with self.subTest(params=params):
                self.assertEqual(self.client.get('/api/sales/orders/', params).status_code, 400)

    def test_filter_counts_and_review_filter_before_pagination(self):
        account = FundAccount.objects.create(name='分页测试 CNY', currency='CNY', creation_idempotency_key='pagination-account')
        pending_ids = [order.id for order in self.orders[:21]]
        for index, order in enumerate(self.orders[:21]):
            note = Privnote.create(note_type='payment', sales_order=order, expires_at=timezone.now() + timedelta(days=1))
            for status in ['needs_more', 'pending']:
                PaymentSubmission.objects.create(
                    sales_order=order, privnote=note, fund_account=account,
                    amount_cny='1.00', status=status,
                    idempotency_key=f'pagination-{index}-{status}', request_hash='test',
                    **({'reviewed_by': self.staff, 'reviewed_at': timezone.now(), 'review_note': '请补充'} if status == 'needs_more' else {}),
                )
        first = self.client.get('/api/sales/orders/').json()
        self.assertEqual((first['count'], first['review_count']), (41, 21))
        seen = []
        for page in [1, 2]:
            data = self.client.get('/api/sales/orders/', {'review_only': 1, 'page': page}).json()
            self.assertEqual((data['count'], data['review_count'], data['pages']), (21, 21, 2))
            self.assertTrue(all(row['payment_review']['status'] == 'pending' for row in data['results']))
            seen.extend(row['id'] for row in data['results'])
        self.assertEqual(seen, sorted(pending_ids, reverse=True))
        target = self.orders[0]
        filtered = self.client.get('/api/sales/orders/', {'q': f'SO-{target.id:06}', 'review_only': 1}).json()
        self.assertEqual((filtered['count'], filtered['review_count']), (1, 1))
        # 最新需补充状态与列表序列化保持一致，不因历史待核实凭证误计。
        latest = PaymentSubmission.objects.filter(sales_order=target, status='pending').get()
        PaymentSubmission.objects.create(
            sales_order=target, privnote=latest.privnote, fund_account=account,
            amount_cny='1.00', status='needs_more', idempotency_key='latest-needs-more', request_hash='test',
            reviewed_by=self.staff, reviewed_at=timezone.now(), review_note='请补充',
        )
        filtered = self.client.get('/api/sales/orders/', {'q': f'SO-{target.id:06}', 'review_only': 1}).json()
        self.assertEqual((filtered['count'], filtered['review_count'], filtered['results']), (0, 0, []))

    def test_recent_sixty_cross_months_sorted_and_capped_before_pagination(self):
        SalesOrder.objects.bulk_create([
            SalesOrder(customer_name='较新订单', operator=self.staff) for _ in range(44)
        ])
        # 旧月份也包含在默认最近订单范围；不能把最近理解成当月。
        SalesOrder.objects.filter(id__in=[o.id for o in self.orders]).update(
            created_at=timezone.now() - timedelta(days=65),
        )
        expected = list(SalesOrder.objects.order_by('-created_at', '-id').values_list('id', flat=True)[:60])
        seen = []
        for page in [1, 2, 3]:
            data = self.client.get('/api/sales/orders/', {'recent_only': 1, 'page': page}).json()
            self.assertEqual((data['count'], data['pages'], data['page'], len(data['results'])), (60, 3, page, 20))
            seen.extend(row['id'] for row in data['results'])
        self.assertEqual(seen, expected)
        last = self.client.get('/api/sales/orders/', {'recent_only': 1, 'page': 4}).json()
        self.assertEqual(last['page'], 3)
        self.assertEqual([row['id'] for row in last['results']], expected[40:])
        unlimited = self.client.get('/api/sales/orders/', {'recent_only': 0}).json()
        self.assertEqual((unlimited['count'], unlimited['pages']), (85, 5))
        large_page = self.client.get('/api/sales/orders/', {'recent_only': 1, 'limit': 100}).json()
        self.assertEqual(len(large_page['results']), 60)
