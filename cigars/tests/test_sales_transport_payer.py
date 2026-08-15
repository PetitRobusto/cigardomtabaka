from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.test import TransactionTestCase

from cigars.models import Brand, Cigar, SalesOrder, User
from cigars.services import OrderServiceError, create_sales_order_draft


class SalesTransportPayerTest(TestCase):
    """Protect the payer rule at service, API, and database boundaries."""

    def setUp(self):
        self.operator = User.objects.create_user(
            'transport-payer-operator', password='pass', is_staff=True,
        )
        brand = Brand.objects.create(
            english_name='Transport Payer Brand', name='承担方品牌',
        )
        self.cigar = Cigar.objects.create(
            brand=brand.english_name,
            english_name='Transport Payer Cigar',
            name='承担方雪茄',
        )

    def item(self):
        return {
            'cigar_id': self.cigar.pk,
            'sale_unit': 'stick',
            'quantity': 1,
            'unit_price': '100.00',
        }

    def create(self, **kwargs):
        return create_sales_order_draft(
            items=[self.item()],
            operator=self.operator,
            customer_name='承担方客户',
            **kwargs,
        )

    def test_customer_payer_adds_transport_charge_to_amount_due(self):
        order = self.create(
            transport_payer='customer',
            customer_transport_fee_cny='30.00',
        )

        self.assertEqual(order.transport_payer, 'customer')
        self.assertEqual(order.customer_transport_fee_cny, Decimal('30.00'))
        self.assertEqual(order.amount_due_cny, Decimal('130.00'))

    def test_company_payer_requires_zero_customer_charge(self):
        with self.assertRaisesMessage(
            OrderServiceError, '公司承担人肉费时客户收费必须为零',
        ):
            self.create(
                transport_payer='company',
                customer_transport_fee_cny='30.00',
            )

        self.assertFalse(SalesOrder.objects.exists())

    def test_company_payer_keeps_transport_out_of_amount_due(self):
        order = self.create(
            transport_payer='company',
            customer_transport_fee_cny='0.00',
        )

        self.assertEqual(order.transport_payer, 'company')
        self.assertEqual(order.amount_due_cny, Decimal('100.00'))

    def test_legacy_calls_infer_payer_from_customer_charge(self):
        customer_paid = self.create(customer_transport_fee_cny='5.00')
        company_paid = self.create(customer_transport_fee_cny='0.00')

        self.assertEqual(customer_paid.transport_payer, 'customer')
        self.assertEqual(company_paid.transport_payer, 'company')

    def test_database_rejects_company_payer_with_customer_charge(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SalesOrder.objects.create(
                customer_name='非法承担方',
                transport_payer='company',
                customer_transport_fee_cny=Decimal('1.00'),
                amount_due_cny=Decimal('1.00'),
            )

    def test_api_persists_and_serializes_explicit_payer(self):
        self.client.force_login(self.operator)
        response = self.client.post(
            '/api/sales/orders/',
            data={
                'items': [self.item()],
                'customer_name': '接口承担方客户',
                'transport_payer': 'company',
                'customer_transport_fee_cny': '0.00',
            },
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='transport-payer-api',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()['sales_order']['transport_payer'], 'company',
        )

    def test_api_rejects_invalid_payer(self):
        self.client.force_login(self.operator)
        response = self.client.post(
            '/api/sales/orders/',
            data={
                'items': [self.item()],
                'transport_payer': 'partner',
                'customer_transport_fee_cny': '0.00',
            },
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='transport-payer-invalid-api',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('承担方', response.json()['error'])


class SalesTransportPayerMigrationTest(TransactionTestCase):
    """Ensure upgrading existing orders preserves their original charge meaning."""

    migrate_from = [('cigars', '0034_purchase_batch_source')]
    migrate_to = [('cigars', '0035_sales_order_transport_payer')]

    def tearDown(self):
        # 迁移测试会改变全局 schema，结束时必须恢复到当前叶节。
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_customer_charges_are_inferred_before_constraint(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        legacy_apps = MigrationExecutor(connection).loader.project_state(
            self.migrate_from,
        ).apps
        LegacySalesOrder = legacy_apps.get_model('cigars', 'SalesOrder')
        charged = LegacySalesOrder.objects.create(
            customer_transport_fee_cny=Decimal('20.00'),
            amount_due_cny=Decimal('20.00'),
        )
        uncharged = LegacySalesOrder.objects.create()

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        SalesOrderModel = executor.loader.project_state(
            self.migrate_to,
        ).apps.get_model('cigars', 'SalesOrder')

        self.assertEqual(
            SalesOrderModel.objects.get(pk=charged.pk).transport_payer,
            'customer',
        )
        self.assertEqual(
            SalesOrderModel.objects.get(pk=uncharged.pk).transport_payer,
            'company',
        )
