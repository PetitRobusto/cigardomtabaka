import json
from datetime import date, datetime
from decimal import Decimal

from django.db import models
from django.test import Client, TestCase
from django.utils import timezone

from cigars.models import Cigar, PurchaseOrder, PurchaseOrderItem, Supplier, User


class InventoryPurchaseApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.operator = User.objects.create_user(
            'inventory-purchase-api', password='pass', is_staff=True,
        )
        self.client.force_login(self.operator)
        self.supplier = Supplier.objects.create(name='哈伯纳斯供应商', phone='123')
        self.cigar = Cigar.objects.create(
            brand='Partagás', name='帕特加斯 D4', english_name='Serie D No.4',
        )

    def post_supplier(self, payload, key):
        return self.client.post(
            '/api/inventory/suppliers/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_supplier_search_create_and_idempotency(self):
        search = self.client.get('/api/inventory/suppliers/', {'q': '哈伯'})
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()['results'][0]['id'], self.supplier.pk)

        payload = {'name': '新供应商', 'phone': '456'}
        created = self.post_supplier(payload, 'supplier-create-1')
        replay = self.post_supplier(payload, 'supplier-create-1')
        conflict = self.post_supplier({'name': '另一个供应商'}, 'supplier-create-1')
        self.assertEqual(created.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(created.json()['supplier']['id'], replay.json()['supplier']['id'])
        self.assertEqual(conflict.status_code, 409)

    def test_purchase_directory_includes_complete_details_and_cancelled_orders(self):
        draft = PurchaseOrder.objects.create(
            supplier=self.supplier,
            rub_total=Decimal('120.00'),
            operator=self.operator,
            draft_business_date=date(2026, 8, 20),
            note='八月采购',
        )
        PurchaseOrderItem.objects.create(
            purchase_order=draft,
            cigar=self.cigar,
            quantity=25,
            box_size=25,
            box_quantity=1,
            unit_price_rub_per_box=Decimal('120.00'),
            packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
        )
        # 目录日期筛选使用业务日期，而不是创建时间；模拟一笔历史创建、当期业务日期的补录单。
        PurchaseOrder.objects.filter(pk=draft.pk).update(
            created_at=timezone.make_aware(datetime(2026, 7, 1, 12, 0)),
        )
        cancelled = PurchaseOrder.objects.create(
            supplier=self.supplier,
            operator=self.operator,
        )
        cancelled.status = PurchaseOrder.Status.CANCELLED
        models.Model.save(cancelled, update_fields=['status'])

        response = self.client.get('/api/inventory/purchases/', {
            'q': '帕特加斯', 'date_from': '2026-08-01', 'date_to': '2026-08-31',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.json()['results']], [draft.pk])
        row = response.json()['results'][0]
        self.assertEqual(row['supplier_name'], self.supplier.name)
        self.assertEqual(row['note'], '八月采购')
        self.assertTrue(row['draft_complete'])
        self.assertEqual(row['items'][0]['brand'], 'Partagás')
        self.assertTrue(row['items'][0]['is_regular'])

        all_orders = self.client.get('/api/inventory/purchases/')
        self.assertEqual(
            {row['id'] for row in all_orders.json()['results']},
            {draft.pk, cancelled.pk},
        )
        self.assertEqual(all_orders.json()['stats']['cancelled'], 1)

    def test_purchase_detail_and_staff_guard(self):
        purchase = PurchaseOrder.objects.create(operator=self.operator)
        detail = self.client.get(f'/api/inventory/purchases/{purchase.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.json()['purchase_order']['draft_complete'])

        self.client.logout()
        denied = self.client.get('/api/inventory/purchases/')
        self.assertEqual(denied.status_code, 403)

    def test_month_paid_total_counts_each_order_once_with_multiple_items(self):
        purchase = PurchaseOrder.objects.create(
            supplier=self.supplier,
            rub_total=Decimal('120.00'),
            operator=self.operator,
        )
        for _ in range(2):
            PurchaseOrderItem.objects.create(
                purchase_order=purchase,
                cigar=self.cigar,
                quantity=25,
                box_size=25,
                box_quantity=1,
                unit_price_rub_per_box=Decimal('60.00'),
                packaging_status=PurchaseOrderItem.PackagingStatus.UNREPRESENTABLE,
            )
        purchase.status = PurchaseOrder.Status.IN_TRANSIT
        purchase.paid_cny_cost = Decimal('10.00')
        purchase.paid_at = timezone.now()
        purchase.payment_idempotency_key = 'monthly-paid-multiple-items'
        models.Model.save(purchase, update_fields=[
            'status', 'paid_cny_cost', 'paid_at', 'payment_idempotency_key',
        ])

        response = self.client.get('/api/inventory/purchases/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['stats']['month_paid_rub'], '120')
