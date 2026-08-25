from datetime import date
import json
import unittest.mock
from decimal import Decimal

from django.db import IntegrityError, close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from accounting.models import Day1Initialization, FundAccount, LedgerPosting
from accounting.services import record_opening_balance
from threading import Barrier, Thread

from cigars.models import (
    Brand,
    SalesReceipt, SalesRefund, SalesShipment, SalesTransportCost,
    Cigar,
    Customer,
    IdempotencyRecord,
    PurchaseBatch,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    StockAllocation,
    StockMovement,
    Supplier,
    User,
)

from cigars.tests.inventory_fixtures import create_purchase_batch


class SalesOrderApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.operator = User.objects.create_user(
            "sales-api-operator", password="pass", is_staff=True
        )
        self.non_staff = User.objects.create_user("sales-api-customer", password="pass")
        # 销售动作是正式账务事实；普通 API fixture 从已完成 Day 1 开始。
        Day1Initialization.objects.create(
            singleton_key="company",
            status=Day1Initialization.Status.COMPLETED,
            business_date=date(2026, 8, 10),
            completed_by=self.operator,
        )
        brand = Brand.objects.create(english_name="API Brand", name="接口品牌")
        self.cigar = Cigar.objects.create(
            brand=brand.english_name,
            english_name="API Cigar",
            name="接口雪茄",
        )

    def login(self, user=None):
        self.client.force_login(user or self.operator)

    def request(self, method, path, body=None, key=None):
        headers = {"content_type": "application/json"}
        if key is not None:
            headers["HTTP_IDEMPOTENCY_KEY"] = key
        return getattr(self.client, method)(
            path,
            data=json.dumps(body) if body is not None else None,
            **headers,
        )

    def body(self, *, quantity=2, sale_unit="stick", sale_quantity=None, box_size=None):
        item = {
            "cigar_id": self.cigar.id,
            "sale_unit": sale_unit,
            "quantity": quantity,
            "unit_price": "20.00",
        }
        if sale_unit == "box":
            item["sale_quantity"] = sale_quantity or 1
            item["box_size"] = box_size or 25
            item["quantity"] = item["sale_quantity"] * item["box_size"]
        return {
            "items": [item],
            "customer_name": "接口客户",
            "customer_transport_fee_cny": "3.00",
            "note": "API 测试",
        }

    def create_batch(self, *, quantity=10, box_size=25, unit_cost="10.00"):
        supplier = Supplier.objects.create(name=f"API Supplier {PurchaseOrder.objects.count()}")
        po = PurchaseOrder.objects.create(
            supplier=supplier,
            rub_total=Decimal("100.00"),
            exchange_rate=Decimal("1.0000"),
            cny_total=Decimal(str(quantity)) * Decimal(unit_cost),
            operator=self.operator,
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=po,
            cigar=self.cigar,
            quantity=quantity,
            box_size=box_size,
            unit_price_rub=Decimal("1.00"),
            unit_price_cny=Decimal(unit_cost),
        )
        boxes, sticks = divmod(quantity, box_size)
        return create_purchase_batch(
            operator=self.operator,
            purchase_order_item=item,
            cigar=self.cigar,
            quantity=quantity,
            remaining=quantity,
            physical_remaining=quantity,
            original_cost_cny=Decimal(str(quantity)) * Decimal(unit_cost),
            original_box_quantity=boxes,
            original_stick_quantity=sticks,
            remaining_cost_cny=Decimal(str(quantity)) * Decimal(unit_cost),
            unit_cost_cny=Decimal(unit_cost),
            physical_box_quantity=boxes,
            physical_stick_quantity=sticks,
            available_box_quantity=boxes,
            available_stick_quantity=sticks,
        )

    def create_order(self, key="create-key", body=None):
        self.login()
        return self.request("post", "/api/sales/orders/", body or self.body(), key)

    def test_non_staff_get_is_forbidden_json(self):
        self.login(self.non_staff)
        response = self.client.get("/api/sales/orders/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("error", response.json())

    def test_create_draft_requires_idempotency_key(self):
        self.login()
        response = self.request("post", "/api/sales/orders/", self.body())
        self.assertEqual(response.status_code, 400)
        self.assertIn("幂等", response.json()["error"])

    def test_create_draft_does_not_reserve_stock(self):
        batch = self.create_batch(quantity=10)
        response = self.create_order()
        self.assertEqual(response.status_code, 201)
        payload = response.json()["sales_order"]
        self.assertEqual(payload["fulfillment_status"], "draft")
        self.assertEqual(payload["items"][0]["cigar_brand"], "API Brand")
        self.assertEqual(payload["items"][0]["cigar_brand_cn"], "")
        self.assertFalse(payload["locked"])
        self.assertEqual(SalesOrder.objects.count(), 1)
        self.assertEqual(StockAllocation.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 10)

    def test_create_draft_links_selected_customer_profile(self):
        customer = Customer.objects.create(name="王先生", phone="13800000000")
        body = self.body()
        body["customer_id"] = customer.id
        body["customer_name"] = customer.name

        response = self.create_order(key="customer-create", body=body)

        self.assertEqual(response.status_code, 201)
        payload = response.json()["sales_order"]
        self.assertEqual(payload["customer_id"], customer.id)
        self.assertEqual(payload["customer"], {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "remark": "",
            "deleted_at": None,
        })

    def test_duplicate_create_key_returns_same_order(self):
        self.create_batch(quantity=10)
        first = self.create_order(key="same-create")
        second = self.create_order(key="same-create")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(SalesOrder.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)

    def test_idempotency_key_conflict_returns_409(self):
        first = self.create_order(key="conflict")
        changed = self.body(quantity=3)
        second = self.create_order(key="conflict", body=changed)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(SalesOrder.objects.count(), 1)

    def test_patch_draft_replaces_items(self):
        created = self.create_order(key="patch-create")
        order_id = created.json()["sales_order"]["id"]
        self.login()
        changed = self.body(quantity=4)
        response = self.request("patch", f"/api/sales/orders/{order_id}/", changed, "patch-key")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["sales_order"]
        self.assertEqual(payload["items"][0]["quantity"], 4)
        self.assertEqual(payload["amount_due_cny"], 83)

    def test_confirm_reserves_sticks_and_locks_order(self):
        batch = self.create_batch(quantity=10)
        created = self.create_order(key="confirm-create")
        order_id = created.json()["sales_order"]["id"]
        self.login()
        response = self.request("post", f"/api/sales/orders/{order_id}/confirm/", {}, "confirm-key")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["sales_order"]
        self.assertEqual(payload["fulfillment_status"], "confirmed")
        self.assertTrue(payload["locked"])
        self.assertEqual(payload["total_cost"], 0)
        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 8)
        self.assertEqual(StockAllocation.objects.count(), 1)

    def test_confirm_reserves_complete_boxes(self):
        batch = self.create_batch(quantity=25, box_size=25)
        created = self.create_order(
            key="box-create",
            body=self.body(sale_unit="box", sale_quantity=1, box_size=25),
        )
        self.login()
        response = self.request(
            "post", f"/api/sales/orders/{created.json()['sales_order']['id']}/confirm/", {}, "box-confirm"
        )
        self.assertEqual(response.status_code, 200)
        batch.refresh_from_db()
        self.assertEqual(batch.available_box_quantity, 0)
        self.assertEqual(batch.available_stick_quantity, 0)

    def test_insufficient_stock_returns_409_and_rolls_back_without_idempotency_success(self):
        self.create_batch(quantity=1)
        response = self.create_order(key="short-create", body=self.body(quantity=2))
        self.login()
        confirm = self.request(
            "post",
            f"/api/sales/orders/{response.json()['sales_order']['id']}/confirm/",
            {},
            "short-confirm",
        )
        self.assertEqual(confirm.status_code, 409)
        self.assertFalse(IdempotencyRecord.objects.filter(key="short-confirm").exists())
        order = SalesOrder.objects.get()
        self.assertEqual(order.fulfillment_status, SalesOrder.FulfillmentStatus.DRAFT)
        self.assertEqual(StockAllocation.objects.count(), 0)

    def test_cancel_releases_reservation(self):
        batch = self.create_batch(quantity=10)
        created = self.create_order(key="cancel-create")
        order_id = created.json()["sales_order"]["id"]
        self.login()
        self.request("post", f"/api/sales/orders/{order_id}/confirm/", {}, "cancel-confirm")
        response = self.request("post", f"/api/sales/orders/{order_id}/cancel/", {}, "cancel-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sales_order"]["fulfillment_status"], "cancelled")
        batch.refresh_from_db()
        self.assertEqual(batch.remaining, 10)
        self.assertEqual(
            set(StockAllocation.objects.values_list("status", flat=True)),
            {StockAllocation.Status.RELEASED},
        )

    def test_draft_can_be_cancelled_and_confirm_cannot_repeat(self):
        self.create_batch(quantity=10)
        created = self.create_order(key="invalid-create")
        order_id = created.json()["sales_order"]["id"]
        self.login()
        cancelled = self.request("post", f"/api/sales/orders/{order_id}/cancel/", {}, "draft-cancel")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["sales_order"]["fulfillment_status"], "cancelled")
        self.assertEqual(cancelled.json()["sales_order"]["available_actions"], [])

        second = self.create_order(key="confirm-create")
        second_id = second.json()["sales_order"]["id"]
        self.login()
        confirmed = self.request("post", f"/api/sales/orders/{second_id}/confirm/", {}, "good-confirm")
        self.assertEqual(confirmed.status_code, 200)
        repeated = self.request("post", f"/api/sales/orders/{second_id}/confirm/", {}, "bad-confirm")
        self.assertEqual(repeated.status_code, 400)

    def test_confirm_idempotency_key_is_scoped_to_order(self):
        self.create_batch(quantity=10)
        first = self.create_order(key="scope-create-one")
        second = self.create_order(key="scope-create-two")
        first_id = first.json()["sales_order"]["id"]
        second_id = second.json()["sales_order"]["id"]
        self.login()
        first_confirm = self.request("post", f"/api/sales/orders/{first_id}/confirm/", {}, "shared-confirm")
        second_confirm = self.request("post", f"/api/sales/orders/{second_id}/confirm/", {}, "shared-confirm")
        self.assertEqual(first_confirm.status_code, 200)
        self.assertEqual(second_confirm.status_code, 409)
        self.assertEqual(SalesOrder.objects.get(id=first_id).fulfillment_status, SalesOrder.FulfillmentStatus.CONFIRMED)
        self.assertEqual(SalesOrder.objects.get(id=second_id).fulfillment_status, SalesOrder.FulfillmentStatus.DRAFT)
        self.assertFalse(StockAllocation.objects.filter(sales_order_item__sales_order_id=second_id).exists())

    def test_list_filters_and_detail(self):
        first = self.create_order(key="list-one")
        second_body = self.body(quantity=3)
        second_body["customer_name"] = "另一个客户"
        second = self.create_order(key="list-two", body=second_body)
        self.login()
        response = self.client.get("/api/sales/orders/?q=另一个&fulfillment_status=draft&limit=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)
        self.assertEqual(response.json()["results"][0]["id"], second.json()["sales_order"]["id"])
        detail = self.client.get(f"/api/sales/orders/{first.json()['sales_order']['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("fifo_cost", detail.json()["sales_order"])

    def test_list_filters_created_date_inclusively_and_rejects_invalid_range(self):
        first = self.create_order(key="date-filter-one")
        second = self.create_order(key="date-filter-two")
        first_id = first.json()["sales_order"]["id"]
        second_id = second.json()["sales_order"]["id"]
        SalesOrder.objects.filter(pk=first_id).update(created_at=timezone.make_aware(timezone.datetime(2026, 8, 9, 23, 59)))
        SalesOrder.objects.filter(pk=second_id).update(created_at=timezone.make_aware(timezone.datetime(2026, 8, 10, 0, 0)))
        self.login()

        response = self.client.get("/api/sales/orders/?date_from=2026-08-10&date_to=2026-08-10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([order["id"] for order in response.json()["results"]], [second_id])
        invalid = self.client.get("/api/sales/orders/?date_from=2026-08-11&date_to=2026-08-10")
        malformed = self.client.get("/api/sales/orders/?date_from=not-a-date")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(malformed.status_code, 400)

    def test_sales_customer_crud_detail_history_and_soft_delete(self):
        self.login()
        created = self.request(
            "post", "/api/sales/customers/",
            {"name": "销售客户甲", "phone": "+7 900 123-45-67", "remark": "偏好木盒"},
            "customer-create",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["customer"]["remark"], "偏好木盒")
        customer_id = created.json()["customer"]["id"]
        order = self.create_order(
            key="customer-history-order",
            body={**self.body(), "customer_id": customer_id, "customer_name": "销售客户甲"},
        )
        self.assertEqual(order.status_code, 201)

        self.login()
        listing = self.client.get("/api/sales/customers/?q=123-45")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["results"][0]["order_count"], 1)
        detail = self.client.get(f"/api/sales/customers/{customer_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["customer"]["recent_orders"][0]["id"], order.json()["sales_order"]["id"])

        updated = self.request(
            "patch", f"/api/sales/customers/{customer_id}/",
            {"name": "销售客户乙", "phone": "+7 900 765-43-21", "remark": "改为周末交付"},
            "customer-update",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["customer"]["name"], "销售客户乙")
        self.assertEqual(updated.json()["customer"]["remark"], "改为周末交付")
        deleted = self.request(
            "delete", f"/api/sales/customers/{customer_id}/", {},
            "customer-delete",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertIsNotNone(deleted.json()["customer"]["deleted_at"])
        self.assertIsNotNone(deleted.json()["customer"]["recent_orders"][0]["customer"]["deleted_at"])
        self.assertEqual(self.client.get(f"/api/sales/customers/{customer_id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/sales/customers/?q=销售客户乙").json()["results"], [])

    def test_sales_customer_write_validation_and_permissions(self):
        self.login()
        invalid = self.request("post", "/api/sales/customers/", {"name": "", "phone": []}, "customer-invalid")
        self.assertEqual(invalid.status_code, 400)
        self.client.logout()
        anonymous = self.client.get("/api/sales/customers/")
        self.assertEqual(anonymous.status_code, 403)

    def test_sales_customer_list_has_fixed_query_count_for_customers_without_orders(self):
        Customer.objects.bulk_create([
            Customer(name=f"无订单客户{index}", phone="") for index in range(10)
        ])
        self.login()

        with self.assertNumQueries(4):
            response = self.client.get("/api/sales/customers/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 10)
        self.assertTrue(all(customer["active_order_count"] == 0 for customer in response.json()["results"]))
        self.assertTrue(all(customer["total_amount_cny"] == 0 for customer in response.json()["results"]))
        self.assertEqual(response.json()["stats"], {
            "customer_count": 10,
            "with_orders_count": 0,
            "recent_customer_count": 0,
            "total_amount_cny": 0.0,
        })

    def test_sales_customer_directory_filters_and_last_order(self):
        self.login()
        active = Customer.objects.create(name="近期客户", phone="13800000001")
        Customer.objects.create(name="无订单客户", phone="13800000002")
        order = self.create_order(
            key="customer-directory-order",
            body={**self.body(), "customer_id": active.id, "customer_name": active.name},
        )
        self.assertEqual(order.status_code, 201)

        with_orders = self.client.get("/api/sales/customers/?activity=with_orders&limit=100")
        without_orders = self.client.get("/api/sales/customers/?activity=without_orders&limit=100")
        recent = self.client.get("/api/sales/customers/?activity=recent&limit=100")

        self.assertEqual([item["name"] for item in with_orders.json()["results"]], ["近期客户"])
        self.assertEqual([item["name"] for item in without_orders.json()["results"]], ["无订单客户"])
        self.assertEqual([item["name"] for item in recent.json()["results"]], ["近期客户"])
        self.assertIsNotNone(with_orders.json()["results"][0]["last_order_at"])
        self.assertEqual(with_orders.json()["stats"]["customer_count"], 2)
        self.assertEqual(with_orders.json()["stats"]["with_orders_count"], 1)
        self.assertEqual(with_orders.json()["stats"]["recent_customer_count"], 1)
        invalid = self.client.get("/api/sales/customers/?activity=unknown")
        self.assertEqual(invalid.status_code, 400)

    def test_deleted_customer_cannot_be_used_for_new_or_updated_order(self):
        customer = Customer.objects.create(name="已删除客户", phone="13800000000")
        customer.deleted_at = timezone.now()
        customer.save(update_fields=["deleted_at"])

        create_body = {**self.body(), "customer_id": customer.id}
        created_with_deleted = self.create_order("deleted-customer-create", create_body)
        self.assertEqual(created_with_deleted.status_code, 400)
        self.assertIn("客户不存在", created_with_deleted.json()["error"])
        self.assertEqual(SalesOrder.objects.count(), 0)

        active_order = self.create_order("active-order")
        order_id = active_order.json()["sales_order"]["id"]
        self.login()
        updated_with_deleted = self.request(
            "patch", f"/api/sales/orders/{order_id}/", create_body,
            "deleted-customer-update",
        )
        self.assertEqual(updated_with_deleted.status_code, 400)
        order = SalesOrder.objects.get(pk=order_id)
        self.assertIsNone(order.customer_id)
        self.assertEqual(order.customer_name, "接口客户")

    def test_customer_unique_constraint_conflicts_return_409(self):
        self.login()
        original_create = Customer.objects.create

        def conflicting_create(*args, **kwargs):
            raise IntegrityError("unique customer name")

        with self.settings(DEBUG=False):
            with unittest.mock.patch.object(Customer.objects, "create", side_effect=conflicting_create):
                response = self.request(
                    "post", "/api/sales/customers/",
                    {"name": "并发重名", "phone": ""}, "customer-race-create",
                )
        self.assertEqual(response.status_code, 409)
        self.assertIn("客户姓名已存在", response.json()["error"])

        first = original_create(name="客户一", phone="")
        second = original_create(name="客户二", phone="")
        with unittest.mock.patch.object(Customer, "save", side_effect=IntegrityError("unique customer name")):
            updated = self.request(
                "patch", f"/api/sales/customers/{second.id}/",
                {"name": "并发改名", "phone": ""}, "customer-race-update",
            )
        self.assertEqual(updated.status_code, 409)
        self.assertIn("客户姓名已存在", updated.json()["error"])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "客户一")
        self.assertEqual(second.name, "客户二")

    def test_list_search_matches_order_number(self):
        created = self.create_order(key="order-number-search")
        order_number = created.json()["sales_order"]["order_number"]
        self.login()
        exact = self.client.get(f"/api/sales/orders/?q={order_number}")
        partial = self.client.get(f"/api/sales/orders/?q={order_number[-3:]}")
        self.assertEqual(exact.status_code, 200)
        self.assertEqual(partial.status_code, 200)
        self.assertEqual([item["order_number"] for item in exact.json()["results"]], [order_number])
        self.assertIn(order_number, [item["order_number"] for item in partial.json()["results"]])

    def test_invalid_json_and_method_are_json_errors(self):
        self.login()
        response = self.client.post(
            "/api/sales/orders/",
            data="{not-json",
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="bad-json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON", response.json()["error"])
        method = self.client.put("/api/sales/orders/", data="{}", content_type="application/json")
        self.assertEqual(method.status_code, 405)
        self.assertEqual(method["Content-Type"], "application/json")

    def test_list_serializes_prefetched_orders_with_fixed_query_count(self):
        for index in range(5):
            self.create_order(key=f"query-order-{index}", body=self.body(quantity=2))
        self.login()
        # Payment-note state is prefetched in one bounded query for the list.
        with self.assertNumQueries(7):
            response = self.client.get("/api/sales/orders/?limit=5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 5)


    def action_order(self, key="action-create"):
        self.create_batch(quantity=10, box_size=25)
        created = self.create_order(key=key, body=self.body(quantity=2))
        order_id = created.json()["sales_order"]["id"]
        self.login()
        confirmed = self.request("post", f"/api/sales/orders/{order_id}/confirm/", {}, f"{key}-confirm")
        self.assertEqual(confirmed.status_code, 200)
        return order_id

    def action_account(self, key="action-account"):
        return FundAccount.objects.create(name=f"API 动作账户 {key}", currency=FundAccount.Currency.CNY, custodian=self.operator, creation_idempotency_key=key)

    def test_ship_action_api_returns_serialized_order_and_shipment(self):
        order_id = self.action_order("api-ship")
        response = self.request("post", f"/api/sales/orders/{order_id}/ship/", {"business_date": "2026-08-10"}, "api-ship-action")
        self.assertIn(response.status_code, (200, 201))
        payload = response.json()["sales_order"]
        self.assertEqual(payload["fulfillment_status"], SalesOrder.FulfillmentStatus.SHIPPED)
        self.assertIn("sales_shipment", payload)

    def test_return_action_api_returns_return_fact_and_actions(self):
        order_id = self.action_order("api-return")
        shipped = self.request(
            "post",
            f"/api/sales/orders/{order_id}/ship/",
            {"business_date": "2026-08-10"},
            "api-return-ship",
        )
        self.assertEqual(shipped.status_code, 200)

        response = self.request(
            "post",
            f"/api/sales/orders/{order_id}/return/",
            {"business_date": "2026-08-11", "reason": "客户整单退回"},
            "api-return-action",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["sales_order"]
        self.assertEqual(payload["fulfillment_status"], SalesOrder.FulfillmentStatus.RETURNED)
        self.assertEqual(payload["sales_return"]["reason"], "客户整单退回")
        self.assertNotIn("return", payload["available_actions"])

    def test_receive_action_api_supports_confirmed_prepayment(self):
        order_id = self.action_order("api-receive")
        account = self.action_account("api-receive-account")
        response = self.request("post", f"/api/sales/orders/{order_id}/receive/", {"amount_cny": "43.00", "fund_account_id": account.id, "business_date": "2026-08-10"}, "api-receive-action")
        self.assertIn(response.status_code, (200, 201))
        payload = response.json()["sales_order"]
        self.assertEqual(payload["payment_status"], SalesOrder.PaymentStatus.PAID)
        self.assertIn("sales_receipt", payload)

    def test_refund_action_api_returns_refund_fact(self):
        order_id = self.action_order("api-refund")
        account = self.action_account("api-refund-account")
        from cigars.sales_accounting import receive_sales_order_payment
        receive_sales_order_payment(order_id=order_id, amount_cny=Decimal("43.00"), fund_account=account, business_date=date(2026, 8, 10), operator=self.operator, idempotency_key="api-refund-setup-receipt")
        self.request("post", f"/api/sales/orders/{order_id}/cancel/", {}, "api-refund-cancel")
        response = self.request("post", f"/api/sales/orders/{order_id}/refund/", {"business_date": "2026-08-10"}, "api-refund-action")
        self.assertIn(response.status_code, (200, 201))
        self.assertEqual(response.json()["sales_order"]["payment_status"], SalesOrder.PaymentStatus.REFUNDED)

    def test_transport_cost_action_api_returns_transport_fact(self):
        order_id = self.action_order("api-transport")
        account = self.action_account("api-transport-account")
        record_opening_balance(
            account, "10.00", "10.00", LedgerPosting.Category.OPENING_CAPITAL,
            date(2026, 8, 10), self.operator, "api-transport-opening",
        )
        from cigars.sales_accounting import ship_sales_order
        ship_sales_order(order_id=order_id, business_date=date(2026, 8, 10), operator=self.operator, idempotency_key="api-transport-setup-ship")
        response = self.request("post", f"/api/sales/orders/{order_id}/transport-cost/", {"actual_cost_cny": "10.00", "fund_account_id": account.id, "business_date": "2026-08-10"}, "api-transport-action")
        self.assertIn(response.status_code, (200, 201))
        self.assertEqual(response.json()["sales_order"]["actual_transport_cost_cny"], 10)

    def test_transport_cost_is_not_available_after_transport_fact_exists(self):
        order_id = self.action_order("api-transport-available-actions")
        account = self.action_account("api-transport-available-actions-account")
        record_opening_balance(
            account, "10.00", "10.00", LedgerPosting.Category.OPENING_CAPITAL,
            date(2026, 8, 10), self.operator, "api-transport-available-actions-opening",
        )
        from cigars.sales_accounting import ship_sales_order
        ship_sales_order(
            order_id=order_id,
            business_date=date(2026, 8, 10),
            operator=self.operator,
            idempotency_key="api-transport-available-actions-ship",
        )
        response = self.request(
            "post",
            f"/api/sales/orders/{order_id}/transport-cost/",
            {
                "actual_cost_cny": "10.00",
                "fund_account_id": account.id,
                "business_date": "2026-08-10",
            },
            "api-transport-available-actions-cost",
        )
        self.assertIn(response.status_code, (200, 201))
        self.assertNotIn("transport_cost", response.json()["sales_order"]["available_actions"])

    def test_sales_order_allocations_include_fifo_cost_trace(self):
        first = self.create_batch(quantity=10, box_size=25, unit_cost="10.00")
        order_id = self.action_order("api-allocation-cost-trace")
        self.login()
        response = self.client.get(f"/api/sales/orders/{order_id}/")
        self.assertEqual(response.status_code, 200)
        allocation = response.json()["sales_order"]["items"][0]["allocations"][0]
        self.assertEqual(allocation["batch_id"], first.id)
        self.assertEqual(allocation["unit_cost_cny"], 10)
        self.assertEqual(allocation["cost_cny"], 20)

    def test_action_api_invalid_input_returns_json_not_500(self):
        order_id = self.action_order("api-invalid-action")
        for path, body, key in ((f"/api/sales/orders/{order_id}/ship/", {"business_date": "not-a-date"}, "api-invalid-date"), (f"/api/sales/orders/{order_id}/receive/", {"amount_cny": "43.001", "fund_account_id": 999999, "business_date": "2026-08-10"}, "api-invalid-receive"), (f"/api/sales/orders/{order_id}/transport-cost/", {"actual_cost_cny": "10.00", "fund_account_id": 999999, "business_date": "2026-08-10"}, "api-invalid-transport")):
            response = self.request("post", path, body, key)
            self.assertIn(response.status_code, (400, 404, 409))
            self.assertLess(response.status_code, 500)
            self.assertEqual(response["Content-Type"], "application/json")


    def test_action_api_notes_must_be_strings(self):
        """正式销售动作拒绝容器备注，避免把畸形 JSON 写入账务事实。"""
        create = self.create_order(
            key="api-invalid-create-note",
            body={**self.body(), "note": {"invalid": True}},
        )
        self.assertEqual(create.status_code, 400)
        self.assertEqual(create.json()["code"], "input_error")

        self.create_batch(quantity=10)
        draft = self.create_order(key="api-invalid-draft-note")
        draft_id = draft.json()["sales_order"]["id"]
        update = self.request(
            "patch", f"/api/sales/orders/{draft_id}/",
            {**self.body(), "note": ["invalid"]},
            "api-invalid-update-note",
        )
        self.assertEqual(update.status_code, 400)
        self.assertEqual(update.json()["code"], "input_error")
        confirm = self.request(
            "post", f"/api/sales/orders/{draft_id}/confirm/",
            {"note": {"invalid": True}}, "api-invalid-confirm-note",
        )
        self.assertEqual(confirm.status_code, 400)
        self.assertEqual(confirm.json()["code"], "input_error")
        confirmed = self.request(
            "post", f"/api/sales/orders/{draft_id}/confirm/",
            {}, "api-valid-confirm-after-invalid-note",
        )
        self.assertEqual(confirmed.status_code, 200)
        cancel = self.request(
            "post", f"/api/sales/orders/{draft_id}/cancel/",
            {"note": ["invalid"]}, "api-invalid-cancel-note",
        )
        self.assertEqual(cancel.status_code, 400)
        self.assertEqual(cancel.json()["code"], "input_error")

        ship_order_id = self.action_order("api-invalid-ship-note")
        ship = self.request(
            "post", f"/api/sales/orders/{ship_order_id}/ship/",
            {"business_date": "2026-08-10", "note": {"invalid": True}},
            "api-invalid-ship-note-action",
        )
        self.assertEqual(ship.status_code, 400)
        self.assertEqual(ship.json()["code"], "input_error")

        transport_order_id = self.action_order("api-invalid-transport-note")
        from cigars.sales_accounting import ship_sales_order
        ship_sales_order(
            order_id=transport_order_id, business_date=date(2026, 8, 10),
            operator=self.operator, idempotency_key="api-invalid-transport-note-ship",
        )
        account = self.action_account("api-invalid-transport-note-account")
        transport = self.request(
            "post", f"/api/sales/orders/{transport_order_id}/transport-cost/",
            {
                "actual_cost_cny": "1.00", "fund_account_id": account.pk,
                "business_date": "2026-08-10", "note": ["invalid"],
            },
            "api-invalid-transport-note-action",
        )
        self.assertEqual(transport.status_code, 400)
        self.assertEqual(transport.json()["code"], "input_error")
    def test_action_api_requires_staff_json(self):
        order_id = self.action_order("api-auth-action")
        self.client.logout()
        anonymous = self.request("post", f"/api/sales/orders/{order_id}/ship/", {"business_date": "2026-08-10"}, "api-anonymous-action")
        self.assertEqual(anonymous.status_code, 403)
        self.login(self.non_staff)
        non_staff = self.request("post", f"/api/sales/orders/{order_id}/ship/", {"business_date": "2026-08-10"}, "api-nonstaff-action")
        self.assertEqual(non_staff.status_code, 403)

    def test_action_api_same_key_replays_and_conflicts_on_changed_body(self):
        order_id = self.action_order("api-idempotent-action")
        first = self.request("post", f"/api/sales/orders/{order_id}/ship/", {"business_date": "2026-08-10"}, "api-action-key")
        second = self.request("post", f"/api/sales/orders/{order_id}/ship/", {"business_date": "2026-08-10"}, "api-action-key")
        changed = self.request("post", f"/api/sales/orders/{order_id}/ship/", {"business_date": "2026-08-11"}, "api-action-key")
        self.assertEqual(first.status_code, second.status_code)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(changed.status_code, 409)


    def test_action_api_invalid_state_and_repeat_are_conflicts(self):
        order_id = self.action_order("api-state-conflict")
        first = self.request("post", f"/api/sales/orders/{order_id}/ship/", {"business_date": "2026-08-10"}, "api-state-ship")
        repeated = self.request("post", f"/api/sales/orders/{order_id}/ship/", {"business_date": "2026-08-10"}, "api-state-ship-other")
        self.assertIn(first.status_code, (200, 201))
        self.assertEqual(repeated.status_code, 409)

    def test_action_api_fund_account_id_requires_positive_integer(self):
        order_id = self.action_order("api-account-type")
        for index, value in enumerate((1.2, True, 0, -1)):
            response = self.request("post", f"/api/sales/orders/{order_id}/receive/", {"amount_cny": "43.00", "fund_account_id": value, "business_date": "2026-08-10"}, f"api-account-type-{index}")
            self.assertEqual(response.status_code, 400)


class SalesOrderApiConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.operator = User.objects.create_user(
            "sales-api-concurrent", password="pass", is_staff=True
        )
        brand = Brand.objects.create(english_name="Concurrent Brand", name="并发品牌")
        self.cigar = Cigar.objects.create(brand=brand.english_name, english_name="Concurrent Cigar", name="并发雪茄")

    def test_same_key_concurrent_create_returns_same_order(self):
        body = {
            "items": [{"cigar_id": self.cigar.id, "sale_unit": "stick", "quantity": 2, "unit_price": "20.00"}],
            "customer_name": "并发客户",
        }
        barrier = Barrier(2)
        results = []

        clients = []
        for _ in range(2):
            client = Client()
            client.force_login(self.operator)
            clients.append(client)

        def worker(client):
            close_old_connections()
            barrier.wait()
            response = client.post(
                "/api/sales/orders/", data=json.dumps(body), content_type="application/json",
                HTTP_IDEMPOTENCY_KEY="concurrent-create",
            )
            results.append((response.status_code, response.json()))
            close_old_connections()

        threads = [Thread(target=worker, args=(client,)) for client in clients]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(results), 2)
        self.assertTrue(all(status == 201 for status, _ in results), results)
        payload_ids = {payload["sales_order"]["id"] for _, payload in results}
        self.assertEqual(len(payload_ids), 1)
        self.assertEqual(payload_ids, set(SalesOrder.objects.values_list("id", flat=True)))
        self.assertEqual(SalesOrder.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)
