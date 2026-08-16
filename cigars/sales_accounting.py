"""销售出库与销售成本记账服务。

本模块只处理已确认订单的出库事实；收款由独立的收款服务处理。
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

from django.db import transaction

from accounting.models import FundAccount, LedgerPosting, LedgerTransaction
from accounting.guards import require_day1_completed
from accounting.mutation_scope import ledger_mutation_scope
from accounting.services import (
    LedgerError,
    PostingInput,
    _post_transaction_once,
    _retry_sqlite_locked,
    _acquire_sqlite_writer_gate,
    reverse_ledger_transaction,
)
from .audit import AgentContext
from . import inventory as inventory_module
from .models import (
    SalesOrder,
    SalesShipment,
    SalesReceipt,
    SalesRefund,
    SalesReturn,
    SalesTransportCost,
)
from .services import (
    OrderServiceError,
    _require_operator,
)


MONEY_PLACES = Decimal("0.01")


def _receipt_credit_category(receipt, amount):
    """返回原收款实际冲销的内部科目。"""
    categories = [
        posting.category
        for posting in receipt.ledger_transaction.postings.all()
        if posting.account_id is None
        and posting.category in {
            LedgerPosting.Category.ACCOUNTS_RECEIVABLE,
            LedgerPosting.Category.CUSTOMER_PREPAYMENTS,
        }
        and posting.amount == -amount
        and posting.cny_amount == -amount
    ]
    if len(categories) != 1:
        raise OrderServiceError("原销售收款流水不完整，不能退款")
    return categories[0]


def _cny_posting(category, amount):
    amount = Decimal(amount).quantize(MONEY_PLACES)
    return PostingInput(
        category=category,
        currency="CNY",
        amount=amount,
        cny_amount=amount,
    )


def _postings_match(transaction_obj, expected):
    """按账户、科目、币种及双金额核对一整组不可变流水。"""
    actual = [
        (row.account_id, row.category, row.currency, row.amount, row.cny_amount)
        for row in transaction_obj.postings.all()
    ]
    return Counter(actual) == Counter(expected)


@_retry_sqlite_locked
@transaction.atomic
def ship_sales_order(*, order_id, business_date, operator, idempotency_key, note="",
                     agent_context=None):
    """出库一张已确认的销售单，并确认 FIFO 成本。

    出库只减少物理库存；确认阶段已经减少 ``remaining``/``available``，
    因此这里不重复修改可售库存。
    """
    # 必须在任何业务读取前取得账务 writer gate，保证 SQLite 下整个操作重试。
    _acquire_sqlite_writer_gate()
    operator_id = getattr(operator, "pk", None)
    if not operator_id:
        raise OrderServiceError("必须提供真实操作人 operator")
    if type(business_date) is not date:
        raise LedgerError("业务日期必须是 date")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise LedgerError("幂等键不能为空")

    try:
        order = SalesOrder.objects.select_for_update().get(pk=order_id)
    except (SalesOrder.DoesNotExist, ValueError, TypeError):
        raise OrderServiceError("销售单不存在")
    existing_shipment = SalesShipment.objects.select_related("ledger_transaction").filter(sales_order=order).first()
    if existing_shipment is not None:
        transaction_obj = existing_shipment.ledger_transaction
        receipt = SalesReceipt.objects.select_related("ledger_transaction").filter(
            sales_order=order,
        ).first()
        receipt_precedes_shipment = (
            receipt is not None
            and receipt.ledger_transaction.effective_sequence
            < transaction_obj.effective_sequence
        )
        settlement_category = (
            LedgerPosting.Category.CUSTOMER_PREPAYMENTS
            if receipt_precedes_shipment
            else LedgerPosting.Category.ACCOUNTS_RECEIVABLE
        )
        goods = order.goods_amount_cny.quantize(MONEY_PLACES)
        transport = order.customer_transport_fee_cny.quantize(MONEY_PLACES)
        amount_due = order.amount_due_cny.quantize(MONEY_PLACES)
        fifo_cost = existing_shipment.fifo_cost_cny.quantize(MONEY_PLACES)
        expected_postings = [
            (None, settlement_category, "CNY", amount_due, amount_due),
            (None, LedgerPosting.Category.SALES_REVENUE, "CNY", -goods, -goods),
            (None, LedgerPosting.Category.CUSTOMER_TRANSPORT_REVENUE, "CNY", -transport, -transport),
            (None, LedgerPosting.Category.COST_OF_GOODS_SOLD, "CNY", fifo_cost, fifo_cost),
            (None, LedgerPosting.Category.INVENTORY, "CNY", -fifo_cost, -fifo_cost),
        ]
        expected_description = note or f"销售单 {order.order_number} 出库"
        if transaction_obj.idempotency_key == idempotency_key:
            if (
                transaction_obj.transaction_type == LedgerTransaction.TransactionType.SALES_SHIPMENT
                and transaction_obj.status == LedgerTransaction.Status.POSTED
                and transaction_obj.business_date == business_date
                and transaction_obj.operator_id == operator_id
                and transaction_obj.description == expected_description
                and transaction_obj.source_type == "sales_order"
                and transaction_obj.source_id == str(order.pk)
                and existing_shipment.business_date == business_date
                and existing_shipment.operator_id == operator_id
                and order.fifo_cost_cny == fifo_cost
                and order.total_cost == fifo_cost
                and _postings_match(transaction_obj, expected_postings)
            ):
                return order
            raise OrderServiceError("出库幂等键参数不匹配")
        raise OrderServiceError("销售单已经出库")
    existing_transaction = LedgerTransaction.objects.filter(idempotency_key=idempotency_key).first()
    if existing_transaction is not None:
        raise OrderServiceError("出库幂等事实不完整")
    operator = _require_operator(operator)
    require_day1_completed()
    if order.fulfillment_status != SalesOrder.FulfillmentStatus.CONFIRMED:
        raise OrderServiceError("只有已确认订单才能出库")
    if order.payment_status not in (
        SalesOrder.PaymentStatus.UNPAID,
        SalesOrder.PaymentStatus.PAID,
    ):
        raise OrderServiceError("销售单不是可出库状态")
    if SalesShipment.objects.filter(sales_order=order).exists():
        raise OrderServiceError("销售单已经出库")

    items = list(
        order.items.select_for_update().select_related("cigar").order_by("id")
    )
    if not items:
        raise OrderServiceError("销售单没有明细")

    # Agent 入口传完整上下文；网页入口沿用默认上下文。
    context = agent_context or AgentContext(
        command_name="ship_sales_order", idempotency_key=idempotency_key,
    )
    try:
        shipment = inventory_module.ship_order(
            order=order, operator=operator, context=context, note=note,
        )
    except inventory_module.InventoryError as error:
        raise OrderServiceError(str(error), details=error.details) from error
    for item in items:
        item_cost = shipment.item_costs[item.pk]
        item.cost = item_cost
        item.unit_cost = (item_cost / item.quantity).quantize(MONEY_PLACES)
        item.profit = (item.revenue - item_cost).quantize(MONEY_PLACES)
        item.save(update_fields=['cost', 'unit_cost', 'profit'])
    total_cost = shipment.total_cost_cny
    goods = order.goods_amount_cny.quantize(MONEY_PLACES)
    transport = order.customer_transport_fee_cny.quantize(MONEY_PLACES)
    amount_due = order.amount_due_cny.quantize(MONEY_PLACES)
    shipment_postings = [
        _cny_posting(
            LedgerPosting.Category.CUSTOMER_PREPAYMENTS
            if order.payment_status == SalesOrder.PaymentStatus.PAID
            else LedgerPosting.Category.ACCOUNTS_RECEIVABLE,
            amount_due,
        ),
        _cny_posting(LedgerPosting.Category.SALES_REVENUE, -goods),
        _cny_posting(LedgerPosting.Category.CUSTOMER_TRANSPORT_REVENUE, -transport),
        _cny_posting(LedgerPosting.Category.COST_OF_GOODS_SOLD, total_cost),
        _cny_posting(LedgerPosting.Category.INVENTORY, -total_cost),
    ]
    ledger = _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.SALES_SHIPMENT,
        business_date=business_date,
        postings=shipment_postings,
        operator=operator,
        idempotency_key=idempotency_key,
        description=note or f"销售单 {order.order_number} 出库",
        source_type="sales_order",
        source_id=str(order.pk),
        _writer_gate=False,
    )
    shipment = SalesShipment.objects.create(
        sales_order=order,
        business_date=business_date,
        fifo_cost_cny=total_cost,
        ledger_transaction=ledger,
        operator=operator,
    )
    order.total_cost = total_cost
    order.fifo_cost_cny = total_cost
    order.total_profit = (amount_due - total_cost).quantize(MONEY_PLACES)
    order.contribution_profit_cny = order.total_profit
    order.fulfillment_status = SalesOrder.FulfillmentStatus.SHIPPED
    order.status = "completed" if order.payment_status == SalesOrder.PaymentStatus.PAID else "shipped"
    order.save(update_fields=[
        "total_cost", "fifo_cost_cny", "total_profit", "contribution_profit_cny",
        "fulfillment_status", "status",
    ])
    return order


@_retry_sqlite_locked
@transaction.atomic
def receive_sales_order_payment(*, order_id, amount_cny, fund_account,
                                business_date, operator, idempotency_key):
    """记录销售单的一次整单人民币收款，支持出库后收款或出库前预收。"""
    _acquire_sqlite_writer_gate()
    if type(business_date) is not date:
        raise LedgerError("业务日期必须是 date")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise LedgerError("幂等键不能为空")
    operator_id = getattr(operator, "pk", None)
    if not operator_id:
        raise LedgerError("必须提供真实操作人 operator")
    try:
        order = SalesOrder.objects.select_for_update().get(pk=order_id)
    except (SalesOrder.DoesNotExist, ValueError, TypeError):
        raise OrderServiceError("销售单不存在")
    try:
        raw_amount = Decimal(str(amount_cny))
        amount = raw_amount.quantize(MONEY_PLACES)
    except Exception as exc:
        raise LedgerError("收款金额必须是有效金额") from exc
    if not raw_amount.is_finite() or raw_amount != amount:
        raise LedgerError("收款金额小数位数超出允许精度")
    if not isinstance(fund_account, FundAccount) or not fund_account.pk:
        raise LedgerError("收款账户必须是已保存的资金账户")
    account_id = fund_account.pk
    existing_transaction = LedgerTransaction.objects.filter(
        idempotency_key=idempotency_key,
    ).first()
    existing = SalesReceipt.objects.select_related("ledger_transaction").filter(sales_order=order).first()
    if existing is not None:
        transaction_obj = existing.ledger_transaction
        postings = list(transaction_obj.postings.order_by("id"))
        valid_replay = (
            transaction_obj == existing_transaction
            and transaction_obj.transaction_type == LedgerTransaction.TransactionType.SALES_RECEIPT
            and transaction_obj.status == LedgerTransaction.Status.POSTED
            and transaction_obj.business_date == business_date
            and transaction_obj.operator_id == operator_id
            and transaction_obj.source_type == "sales_order"
            and transaction_obj.source_id == str(order.pk)
            and existing.amount_cny == amount
            and existing.fund_account_id == account_id
            and existing.business_date == business_date
            and existing.operator_id == operator_id
            and len(postings) == 2
            and postings[0].account_id == account_id
            and postings[0].category == ""
            and postings[0].currency == FundAccount.Currency.CNY
            and postings[0].amount == amount
            and postings[0].cny_amount == amount
            and postings[1].category in (
                LedgerPosting.Category.ACCOUNTS_RECEIVABLE,
                LedgerPosting.Category.CUSTOMER_PREPAYMENTS,
            )
            and postings[1].currency == FundAccount.Currency.CNY
            and postings[1].amount == -amount
            and postings[1].cny_amount == -amount
        )
        if not valid_replay:
            raise OrderServiceError("销售收款幂等键参数不匹配")
        return existing
    if existing_transaction is not None:
        raise OrderServiceError("销售收款幂等键已用于其他业务")
    require_day1_completed()
    operator = _require_operator(operator)
    if order.fulfillment_status not in (
        SalesOrder.FulfillmentStatus.CONFIRMED,
        SalesOrder.FulfillmentStatus.SHIPPED,
    ):
        raise OrderServiceError("只有已确认或已出库订单才能收款")
    if amount <= 0 or amount != order.amount_due_cny.quantize(MONEY_PLACES):
        raise OrderServiceError("收款金额必须等于销售单应收总额")
    try:
        account = FundAccount.objects.select_for_update().get(pk=account_id)
    except FundAccount.DoesNotExist:
        raise LedgerError("收款账户不存在")
    if not account.is_active:
        raise LedgerError("账户已停用")
    if account.currency != FundAccount.Currency.CNY:
        raise LedgerError("销售收款账户必须是人民币账户")
    if order.payment_status != SalesOrder.PaymentStatus.UNPAID:
        raise OrderServiceError("销售单不是待收款状态")
    credit_category = (
        LedgerPosting.Category.CUSTOMER_PREPAYMENTS
        if order.fulfillment_status == SalesOrder.FulfillmentStatus.CONFIRMED
        else LedgerPosting.Category.ACCOUNTS_RECEIVABLE
    )
    ledger = _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.SALES_RECEIPT,
        business_date=business_date,
        postings=[
            PostingInput(account=account, currency=FundAccount.Currency.CNY,
                         amount=amount, cny_amount=amount),
            _cny_posting(credit_category, -amount),
        ],
        operator=operator, idempotency_key=idempotency_key,
        description=f"销售单 {order.order_number} 收款",
        source_type="sales_order", source_id=str(order.pk), _writer_gate=False,
    )
    receipt = SalesReceipt.objects.create(
        sales_order=order, amount_cny=amount, fund_account=account,
        business_date=business_date, ledger_transaction=ledger, operator=operator,
    )
    order.payment_status = SalesOrder.PaymentStatus.PAID
    order.status = "paid" if order.fulfillment_status == SalesOrder.FulfillmentStatus.CONFIRMED else "completed"
    order.save(update_fields=["payment_status", "status"])
    return receipt


@_retry_sqlite_locked
@transaction.atomic
def return_sales_order(*, order_id, business_date, operator, idempotency_key,
                       reason, agent_context=None):
    """整单退回已出库商品并冲正销售出库。"""
    _acquire_sqlite_writer_gate()
    operator = _require_operator(operator)
    require_day1_completed()
    reason = str(reason or '').strip()
    if not reason:
        raise OrderServiceError('退货原因不能为空')
    order = SalesOrder.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        raise OrderServiceError('销售单不存在')
    existing = SalesReturn.objects.select_related(
        'ledger_transaction', 'sales_shipment__ledger_transaction',
    ).filter(sales_order=order).first()
    if existing is not None:
        reverse_ledger_transaction(
            original_transaction=existing.sales_shipment.ledger_transaction,
            business_date=business_date, operator=operator,
            idempotency_key=idempotency_key, reason=reason,
        )
        return existing
    if order.fulfillment_status != SalesOrder.FulfillmentStatus.SHIPPED:
        raise OrderServiceError('只有已出库订单才能整单退货')
    shipment = SalesShipment.objects.select_related('ledger_transaction').filter(
        sales_order=order,
    ).first()
    if shipment is None:
        raise OrderServiceError('销售出库事实不存在')
    context = agent_context or AgentContext(
        command_name='return_sales_order', idempotency_key=idempotency_key,
    )
    try:
        returned_cost = inventory_module.return_order(
            order=order, operator=operator, context=context, note=reason,
            expected_cost_cny=shipment.fifo_cost_cny,
        )
    except inventory_module.InventoryError as error:
        raise OrderServiceError(str(error), details=error.details) from error
    if returned_cost != shipment.fifo_cost_cny:
        raise OrderServiceError('退回库存成本与原销售出库不一致')
    reversal = reverse_ledger_transaction(
        original_transaction=shipment.ledger_transaction,
        business_date=business_date, operator=operator,
        idempotency_key=idempotency_key, reason=reason,
    )
    with ledger_mutation_scope(
        reason='sales_return_fact', model='cigars.SalesReturn', operator=operator,
    ):
        sales_return = SalesReturn.objects.create(
            sales_order=order, sales_shipment=shipment,
            amount_cny=order.amount_due_cny, fifo_cost_cny=returned_cost,
            ledger_transaction=reversal, business_date=business_date,
            operator=operator, reason=reason,
        )
    order.fulfillment_status = SalesOrder.FulfillmentStatus.RETURNED
    order.status = 'returned'
    if order.payment_status == SalesOrder.PaymentStatus.PAID:
        order.payment_status = SalesOrder.PaymentStatus.REFUND_PENDING
    order.save(update_fields=['fulfillment_status', 'payment_status', 'status'])
    return sales_return


@_retry_sqlite_locked
@transaction.atomic
def refund_sales_order_payment(*, order_id, business_date, operator, idempotency_key):
    """退回已取消或已退货销售单的整笔收款。"""
    _acquire_sqlite_writer_gate()
    operator_id = getattr(operator, "pk", None)
    if not operator_id:
        raise OrderServiceError("必须提供真实操作人 operator")
    if type(business_date) is not date:
        raise LedgerError("业务日期必须是 date")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise LedgerError("幂等键不能为空")
    try:
        order = SalesOrder.objects.select_for_update().get(pk=order_id)
    except (SalesOrder.DoesNotExist, ValueError, TypeError):
        raise OrderServiceError("销售单不存在")

    existing_tx = LedgerTransaction.objects.filter(idempotency_key=idempotency_key).first()
    receipt = SalesReceipt.objects.select_related(
        "fund_account", "ledger_transaction",
    ).filter(sales_order=order).first()
    existing = SalesRefund.objects.select_related("ledger_transaction").filter(sales_order=order).first()
    if existing is not None:
        if receipt is None:
            raise OrderServiceError("销售单没有可退款的收款")
        credit_category = _receipt_credit_category(receipt, existing.amount_cny)
        tx = existing.ledger_transaction
        postings = list(tx.postings.all())
        account_postings = [
            posting for posting in postings
            if posting.account_id == existing.fund_account_id
            and posting.category == ""
            and posting.currency == FundAccount.Currency.CNY
            and posting.amount == -existing.amount_cny
            and posting.cny_amount == -existing.amount_cny
        ]
        offset_postings = [
            posting for posting in postings
            if posting.account_id is None
            and posting.category == credit_category
            and posting.currency == FundAccount.Currency.CNY
            and posting.amount == existing.amount_cny
            and posting.cny_amount == existing.amount_cny
        ]
        valid = (
            existing_tx == tx
            and tx.transaction_type == LedgerTransaction.TransactionType.SALES_REFUND
            and tx.status == LedgerTransaction.Status.POSTED
            and tx.business_date == business_date
            and tx.operator_id == operator_id
            and tx.source_type == "sales_order"
            and tx.source_id == str(order.pk)
            and existing.business_date == business_date
            and existing.operator_id == operator_id
            and len(postings) == 2
            and len(account_postings) == 1
            and len(offset_postings) == 1
        )
        if not valid:
            raise OrderServiceError("销售退款幂等键参数不匹配")
        return existing
    if existing_tx is not None:
        raise OrderServiceError("销售退款幂等键已用于其他业务")
    operator = _require_operator(operator)
    require_day1_completed()

    if receipt is None:
        raise OrderServiceError("销售单没有可退款的收款")
    receipt_tx = receipt.ledger_transaction
    receipt_postings = list(receipt_tx.postings.order_by("id"))
    amount = receipt.amount_cny.quantize(MONEY_PLACES)
    account = FundAccount.objects.select_for_update().get(pk=receipt.fund_account_id)
    account_postings = [
        posting for posting in receipt_postings
        if posting.account_id == account.pk
        and posting.category == ""
        and posting.currency == FundAccount.Currency.CNY
        and posting.amount == amount
        and posting.cny_amount == amount
    ]
    credit_category = _receipt_credit_category(receipt, amount)
    credit_postings = [
        posting for posting in receipt_postings
        if posting.account_id is None
        and posting.category == credit_category
        and posting.currency == FundAccount.Currency.CNY
        and posting.amount == -amount
        and posting.cny_amount == -amount
    ]
    valid_receipt = (
        receipt_tx.transaction_type == LedgerTransaction.TransactionType.SALES_RECEIPT
        and receipt_tx.status == LedgerTransaction.Status.POSTED
        and receipt_tx.source_type == "sales_order"
        and receipt_tx.source_id == str(order.pk)
        and receipt_tx.business_date == receipt.business_date
        and receipt_tx.operator_id == receipt.operator_id
        and len(receipt_postings) == 2
        and len(account_postings) == 1
        and len(credit_postings) == 1
    )
    if not valid_receipt:
        raise OrderServiceError("原销售收款流水不完整，不能退款")
    if (
        order.fulfillment_status not in {
            SalesOrder.FulfillmentStatus.CANCELLED,
            SalesOrder.FulfillmentStatus.RETURNED,
        }
        or order.payment_status != SalesOrder.PaymentStatus.REFUND_PENDING
    ):
        raise OrderServiceError("销售单不是待退款状态")
    if not account.is_active or account.currency != FundAccount.Currency.CNY:
        raise LedgerError("原收款账户必须是启用的人民币账户")
    ledger = _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.SALES_REFUND,
        business_date=business_date,
        postings=[
            PostingInput(account=account, currency=FundAccount.Currency.CNY, amount=-amount, cny_amount=-amount),
            _cny_posting(credit_category, amount),
        ],
        operator=operator, idempotency_key=idempotency_key,
        description=f"销售单 {order.order_number} 退款",
        source_type="sales_order", source_id=str(order.pk), _writer_gate=False,
    )
    refund = SalesRefund.objects.create(
        sales_order=order, amount_cny=amount, fund_account=account,
        business_date=business_date, ledger_transaction=ledger, operator=operator,
    )
    order.payment_status = SalesOrder.PaymentStatus.REFUNDED
    order.save(update_fields=["payment_status"])
    return refund


@_retry_sqlite_locked
@transaction.atomic
def record_sales_transport_cost(*, order_id, actual_cost_cny, fund_account,
                                business_date, operator, idempotency_key, note=""):
    """记录已出库销售单实际承担的人肉成本。"""
    _acquire_sqlite_writer_gate()
    if type(business_date) is not date:
        raise LedgerError("业务日期必须是 date")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise LedgerError("幂等键不能为空")
    operator_id = getattr(operator, "pk", None)
    if not operator_id:
        raise LedgerError("必须提供真实操作人 operator")
    try:
        order = SalesOrder.objects.select_for_update().get(pk=order_id)
    except (SalesOrder.DoesNotExist, ValueError, TypeError):
        raise OrderServiceError("销售单不存在")
    try:
        raw_amount = Decimal(str(actual_cost_cny))
        amount = raw_amount.quantize(MONEY_PLACES)
    except Exception as exc:
        raise LedgerError("人肉成本必须是有效金额") from exc
    if not raw_amount.is_finite() or raw_amount != amount:
        raise LedgerError("人肉成本小数位数超出允许精度")
    if not isinstance(fund_account, FundAccount) or not fund_account.pk:
        raise LedgerError("付款账户必须是已保存的资金账户")
    account_id = fund_account.pk
    existing_tx = LedgerTransaction.objects.filter(idempotency_key=idempotency_key).first()
    existing = SalesTransportCost.objects.select_related("ledger_transaction").filter(sales_order=order).first()
    if existing is not None:
        tx = existing.ledger_transaction
        expected_postings = [
            (None, LedgerPosting.Category.TRANSPORT_EXPENSE, "CNY", amount, amount),
            (account_id, LedgerPosting.Category.FUND_ACCOUNT, "CNY", -amount, -amount),
        ]
        replay_changed = (
            existing_tx != tx
            or tx.transaction_type != LedgerTransaction.TransactionType.SALES_TRANSPORT_COST
            or tx.status != LedgerTransaction.Status.POSTED
            or tx.business_date != business_date
            or tx.operator_id != operator_id
            or tx.source_type != "sales_order"
            or tx.source_id != str(order.pk)
            or existing.actual_cost_cny != amount
            or existing.fund_account_id != account_id
            or existing.business_date != business_date
            or existing.operator_id != operator_id
            or existing.note != (note or "")
            or not _postings_match(tx, expected_postings)
        )
        if replay_changed:
            raise OrderServiceError("人肉成本幂等键参数不匹配")
        return existing
    if existing_tx is not None:
        raise OrderServiceError("人肉成本幂等键已用于其他业务")
    require_day1_completed()
    operator = _require_operator(operator)
    if order.fulfillment_status not in {
        SalesOrder.FulfillmentStatus.SHIPPED,
        SalesOrder.FulfillmentStatus.RETURNED,
    }:
        raise OrderServiceError("只有已出库或已退货订单才能记录人肉成本")
    if amount <= 0:
        raise LedgerError("人肉成本必须是正的两位小数")
    account = FundAccount.objects.select_for_update().filter(pk=account_id).first()
    if account is None:
        raise LedgerError("付款账户不存在")
    if not account.is_active or account.currency != FundAccount.Currency.CNY:
        raise LedgerError("人肉成本账户必须是启用的人民币账户")
    ledger = _post_transaction_once(
        transaction_type=LedgerTransaction.TransactionType.SALES_TRANSPORT_COST,
        business_date=business_date,
        postings=[
            _cny_posting(LedgerPosting.Category.TRANSPORT_EXPENSE, amount),
            PostingInput(account=account, currency=FundAccount.Currency.CNY, amount=-amount, cny_amount=-amount),
        ],
        operator=operator, idempotency_key=idempotency_key,
        description=f"销售单 {order.order_number} 人肉成本",
        source_type="sales_order", source_id=str(order.pk), _writer_gate=False,
    )
    cost = SalesTransportCost.objects.create(
        sales_order=order, actual_cost_cny=amount, fund_account=account,
        business_date=business_date, ledger_transaction=ledger, operator=operator, note=note or "",
    )
    order.actual_transport_cost_cny = amount
    order.contribution_profit_cny = (order.total_profit - amount).quantize(MONEY_PLACES)
    order.save(update_fields=["actual_transport_cost_cny", "contribution_profit_cny"])
    return cost
