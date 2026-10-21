import json
from datetime import date
from threading import Barrier, Thread

from django.db import close_old_connections
from django.test import Client, TransactionTestCase

from accounting.models import Day1Initialization, FundAccount
from cigars.models import SalesOrder, SalesReceipt, User


class PartialReceiptsConcurrencyTest(TransactionTestCase):
    def test_competing_receipts_cannot_overcollect(self):
        self._compete(same_key=False)

    def test_same_key_concurrent_receipts_post_once(self):
        self._compete(same_key=True)

    def _compete(self, same_key):
        operator = User.objects.create_user('partial-concurrent', is_staff=True)
        Day1Initialization.objects.create(singleton_key='company', status='completed', business_date=date(2026, 9, 11), completed_by=operator)
        account = FundAccount.objects.create(name='并发收款', currency='CNY', creation_idempotency_key='concurrent-account')
        order = SalesOrder.objects.create(operator=operator, amount_due_cny=100, goods_amount_cny=100, fulfillment_status='confirmed', payment_status='unpaid')
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(operator)
        barrier = Barrier(2)
        results = []

        def worker(index):
            close_old_connections()
            barrier.wait()
            response = clients[index].post(f'/api/sales/orders/{order.pk}/receive/',
                data=json.dumps({'amount_cny': '60', 'fund_account_id': account.pk, 'business_date': '2026-09-11'}),
                content_type='application/json', HTTP_IDEMPOTENCY_KEY=f'competing-receipt-{0 if same_key else index}')
            results.append((response.status_code, response.json()))
            close_old_connections()

        threads = [Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sorted(status for status, _ in results), [200, 200] if same_key else [200, 409], results)
        self.assertEqual(SalesReceipt.objects.count(), 1)
        self.assertEqual(SalesReceipt.objects.get().amount_cny, 60)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'partial')
