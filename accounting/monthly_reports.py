import calendar
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Min, Sum

from accounting.business_time import moscow_business_date
from accounting.models import LedgerPosting, LedgerTransaction
from accounting.selectors import _operating_profit_facts, _sum_category
from cigars.models import (
    PurchaseBatch,
    SalesOrder,
    SalesReceipt,
    SalesRefund,
    SalesReturn,
    SalesShipment,
    SalesTransportCost,
)


MONEY = Decimal('0.01')
RATE = Decimal('0.0001')


def _money(value):
    return (value or Decimal('0.00')).quantize(MONEY)


def _month_bounds(month):
    if not hasattr(month, 'year') or not hasattr(month, 'month'):
        raise ValueError('month 必须是 date')
    start = month.replace(day=1)
    end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    return start, end


def _period(month):
    start, calendar_end = _month_bounds(month)
    today = moscow_business_date()
    current_month = today.replace(day=1)
    if start > current_month:
        raise ValueError('month 不能晚于当前业务月份')
    is_current = start == current_month
    end = today if is_current else calendar_end
    previous_calendar_end = start - timedelta(days=1)
    previous_start = previous_calendar_end.replace(day=1)
    if is_current:
        elapsed_days = (end - start).days
        previous_end = min(
            previous_calendar_end,
            previous_start + timedelta(days=elapsed_days),
        )
    else:
        previous_end = previous_calendar_end
    return {
        'start': start,
        'end': end,
        'is_current': is_current,
        'previous_start': previous_start,
        'previous_end': previous_end,
    }


def _ratio(profit, revenue):
    revenue = _money(revenue)
    if revenue <= 0:
        return None
    return (profit / revenue).quantize(RATE)


def _profit_facts(*, start, end):
    facts = _operating_profit_facts(start=start, end=end)
    sales_revenue = _money(
        -facts['sales_revenue_cny'] - facts['customer_transport_revenue_cny']
    )
    product_cost = _money(facts['cost_of_goods_sold_cny'])
    human_cost = _money(
        facts['transport_expense_cny'] + facts['transport_settlement_expense_cny']
    )
    expenses = {
        'salary_cny': _money(facts['salary_expense_cny']),
        'rent_cny': _money(facts['rent_expense_cny']),
        'utilities_cny': _money(facts['utilities_expense_cny']),
        'professional_services_cny': _money(facts['professional_expense_cny']),
        'financial_cny': _money(facts['interest_expense_cny']),
        'other_cny': _money(facts['other_expense_cny']),
    }
    operating_expenses = _money(sum(expenses.values(), Decimal('0.00')))
    sales_profit = _money(sales_revenue - product_cost - human_cost)
    core_profit = _money(sales_profit - operating_expenses)
    inventory_adjustment = _money(
        facts['inventory_adjustment_gain_cny'] - facts['inventory_adjustment_loss_cny']
    )
    reconciliation_adjustment = _money(
        facts['reconciliation_gain_cny'] - facts['reconciliation_loss_cny']
    )
    net_profit = _money(core_profit + inventory_adjustment + reconciliation_adjustment)
    return {
        'sales_revenue_cny': sales_revenue,
        'product_cost_cny': product_cost,
        'human_cost_cny': human_cost,
        'sales_profit_cny': sales_profit,
        'sales_profit_rate': _ratio(sales_profit, sales_revenue),
        'operating_expenses_cny': operating_expenses,
        'operating_expense_breakdown': expenses,
        'core_operating_profit_cny': core_profit,
        'inventory_adjustment_cny': inventory_adjustment,
        'reconciliation_adjustment_cny': reconciliation_adjustment,
        'net_operating_profit_cny': net_profit,
    }


def _order_items(order):
    return list(order.items.all())


def _allocate(total, items, value_getter):
    """Allocate money deterministically; the final item receives rounding residue."""
    total = _money(total)
    if not items:
        return []
    weights = [Decimal(value_getter(item) or 0) for item in items]
    weight_total = sum(weights, Decimal('0.00'))
    if weight_total <= 0:
        weights = [Decimal('1') for _item in items]
        weight_total = Decimal(len(items))
    allocated = Decimal('0.00')
    result = []
    for index, weight in enumerate(weights):
        if index == len(items) - 1:
            amount = total - allocated
        else:
            amount = _money(total * weight / weight_total)
            allocated += amount
        result.append(_money(amount))
    return result


def _empty_rank_value(name):
    return {
        'name': name,
        'revenue': Decimal('0.00'),
        'quantity': 0,
        'cost': Decimal('0.00'),
        'human_cost': Decimal('0.00'),
    }


def _add_rank_value(row, *, revenue=Decimal('0.00'), quantity=0,
                    cost=Decimal('0.00'), human_cost=Decimal('0.00')):
    row['revenue'] += revenue
    row['quantity'] += quantity
    row['cost'] += cost
    row['human_cost'] += human_cost


def _rank_rows(rows):
    result = []
    for key, values in rows.items():
        revenue = _money(values['revenue'])
        cost = _money(values['cost'])
        human_cost = _money(values['human_cost'])
        profit = _money(revenue - cost - human_cost)
        result.append({
            'key': key,
            'name': values['name'],
            'net_sales_revenue_cny': revenue,
            'quantity': values['quantity'],
            'product_cost_cny': cost,
            'human_cost_cny': human_cost,
            'sales_profit_cny': profit,
            'sales_profit_rate': _ratio(profit, revenue),
        })
    return sorted(
        result,
        key=lambda row: (-row['sales_profit_cny'], -row['net_sales_revenue_cny'], str(row['key'])),
    )


def _apply_item_dimensions(brand_rows, product_rows, items, *, revenues, costs,
                           human_costs, quantity_sign):
    for item, revenue, cost, human_cost in zip(items, revenues, costs, human_costs):
        brand_key = item.cigar.brand
        brand = brand_rows.setdefault(brand_key, _empty_rank_value(brand_key))
        product_name = f'{item.cigar.brand} {item.cigar.name or item.cigar.english_name}'
        product = product_rows.setdefault(
            item.cigar_id, _empty_rank_value(product_name),
        )
        values = {
            'revenue': revenue,
            'quantity': item.quantity * quantity_sign,
            'cost': cost,
            'human_cost': human_cost,
        }
        _add_rank_value(brand, **values)
        _add_rank_value(product, **values)


def _rankings(*, start, end, total_human_cost):
    shipments = list(
        SalesShipment.objects.filter(
            business_date__gte=start,
            business_date__lte=end,
            ledger_transaction__status=LedgerTransaction.Status.POSTED,
        ).select_related('sales_order', 'sales_order__customer').prefetch_related(
            'sales_order__items__cigar',
        )
    )
    returns = list(
        SalesReturn.objects.filter(
            business_date__gte=start,
            business_date__lte=end,
            ledger_transaction__status=LedgerTransaction.Status.POSTED,
        ).select_related('sales_order', 'sales_order__customer').prefetch_related(
            'sales_order__items__cigar',
        )
    )
    transport_costs = list(
        SalesTransportCost.objects.filter(
            sales_order__sales_shipment__business_date__gte=start,
            sales_order__sales_shipment__business_date__lte=end,
            sales_order__sales_shipment__ledger_transaction__status=(
                LedgerTransaction.Status.POSTED
            ),
            ledger_transaction__status=LedgerTransaction.Status.POSTED,
        ).select_related('sales_order', 'sales_order__customer').prefetch_related(
            'sales_order__items__cigar',
        )
    )

    brand_rows = {}
    product_rows = {}
    customer_rows = {}

    for shipment in shipments:
        order = shipment.sales_order
        items = _order_items(order)
        item_revenue = [item.revenue for item in items]
        transport_revenue = (
            order.customer_transport_fee_cny
            if order.transport_payer == SalesOrder.TransportPayer.CUSTOMER
            else Decimal('0.00')
        )
        transport_allocations = _allocate(transport_revenue, items, lambda item: item.revenue)
        revenues = [
            _money(item.revenue + transport)
            for item, transport in zip(items, transport_allocations)
        ]
        costs = [_money(item.cost) for item in items]
        zeros = [Decimal('0.00') for _item in items]
        _apply_item_dimensions(
            brand_rows, product_rows, items,
            revenues=revenues, costs=costs, human_costs=zeros, quantity_sign=1,
        )
        if order.customer_id:
            customer = customer_rows.setdefault(
                order.customer_id, _empty_rank_value(order.customer.name),
            )
            _add_rank_value(
                customer,
                revenue=_money(sum(item_revenue, Decimal('0.00')) + transport_revenue),
                quantity=sum(item.quantity for item in items),
                cost=_money(shipment.fifo_cost_cny),
            )

    for returned in returns:
        order = returned.sales_order
        items = _order_items(order)
        revenues = [
            -amount for amount in _allocate(returned.amount_cny, items, lambda item: item.revenue)
        ]
        costs = [
            -amount for amount in _allocate(returned.fifo_cost_cny, items, lambda item: item.cost)
        ]
        zeros = [Decimal('0.00') for _item in items]
        _apply_item_dimensions(
            brand_rows, product_rows, items,
            revenues=revenues, costs=costs, human_costs=zeros, quantity_sign=-1,
        )
        if order.customer_id:
            customer = customer_rows.setdefault(
                order.customer_id, _empty_rank_value(order.customer.name),
            )
            _add_rank_value(
                customer,
                revenue=-_money(returned.amount_cny),
                quantity=-sum(item.quantity for item in items),
                cost=-_money(returned.fifo_cost_cny),
            )

    allocated_human_cost = Decimal('0.00')
    for cost_fact in transport_costs:
        order = cost_fact.sales_order
        items = _order_items(order)
        allocations = _allocate(cost_fact.actual_cost_cny, items, lambda item: item.revenue)
        zeros = [Decimal('0.00') for _item in items]
        _apply_item_dimensions(
            brand_rows, product_rows, items,
            revenues=zeros, costs=zeros, human_costs=allocations, quantity_sign=0,
        )
        allocated_human_cost += cost_fact.actual_cost_cny
        if order.customer_id:
            customer = customer_rows.setdefault(
                order.customer_id, _empty_rank_value(order.customer.name),
            )
            _add_rank_value(customer, human_cost=_money(cost_fact.actual_cost_cny))

    return {
        'default_sort': 'sales_profit_cny',
        'allocation_rule': (
            '客户承担的人肉费收入和订单实际人肉成本均归属履约月，并按商品收入'
            '占比分摊，最后一行承接分币尾差；运输结算费用不分摊到排行。'
        ),
        'unallocated_human_cost_cny': _money(total_human_cost - allocated_human_cost),
        'brands': _rank_rows(brand_rows),
        'products': _rank_rows(product_rows),
        'customers': _rank_rows(customer_rows),
        '_shipments': shipments,
        '_returns': returns,
    }


def _customer_summary(shipments, *, start, end):
    counts = defaultdict(int)
    for shipment in shipments:
        customer_id = shipment.sales_order.customer_id
        if customer_id:
            counts[customer_id] += 1
    first_dates = {
        row['sales_order__customer_id']: row['first_business_date']
        for row in SalesShipment.objects.filter(
            sales_order__customer__isnull=False,
            business_date__lte=end,
            ledger_transaction__status=LedgerTransaction.Status.POSTED,
        ).values('sales_order__customer_id').annotate(
            first_business_date=Min('business_date'),
        )
    }
    new_count = sum(
        start <= first_dates[customer_id] <= end
        for customer_id in counts
    )
    repeat_count = sum(
        first_dates[customer_id] < start or order_count >= 2
        for customer_id, order_count in counts.items()
    )
    return {
        'fulfilled_customer_count': len(counts),
        'new_customer_count': new_count,
        'repeat_customer_count': repeat_count,
        'guest_orders_excluded': True,
    }


def _cash_facts(*, start, end):
    receipts = SalesReceipt.objects.filter(
        business_date__gte=start,
        business_date__lte=end,
        ledger_transaction__status=LedgerTransaction.Status.POSTED,
    ).aggregate(total=Sum('amount_cny'))['total'] or Decimal('0.00')
    refunds = SalesRefund.objects.filter(
        business_date__gte=start,
        business_date__lte=end,
        ledger_transaction__status=LedgerTransaction.Status.POSTED,
    ).aggregate(total=Sum('amount_cny'))['total'] or Decimal('0.00')
    return {
        'sales_receipts_cny': _money(receipts),
        'refunds_cny': _money(refunds),
        'net_receipts_cny': _money(receipts - refunds),
        'accounts_receivable_cny': _money(_sum_category(
            LedgerPosting.Category.ACCOUNTS_RECEIVABLE, end=end,
        )),
        'customer_prepayments_cny': _money(-_sum_category(
            LedgerPosting.Category.CUSTOMER_PREPAYMENTS, end=end,
        )),
    }


def _inventory_warnings(*, end, is_current):
    if not is_current:
        return {
            'status': 'unavailable',
            'reason': '历史商品级月末库存成本尚无独立业务日期快照',
            'items': [],
        }
    inventory = list(
        PurchaseBatch.objects.filter(physical_remaining__gt=0).values(
            'cigar_id', 'cigar__brand', 'cigar__name', 'cigar__english_name',
        ).annotate(
            cost_cny=Sum('remaining_cost_cny'),
            quantity=Sum('physical_remaining'),
        )
    )
    velocity_start = end - timedelta(days=89)
    sold = defaultdict(int)
    recent_shipments = SalesShipment.objects.filter(
        business_date__gte=velocity_start,
        business_date__lte=end,
        ledger_transaction__status=LedgerTransaction.Status.POSTED,
    ).prefetch_related('sales_order__items')
    for shipment in recent_shipments:
        for item in shipment.sales_order.items.all():
            sold[item.cigar_id] += item.quantity
    warnings = []
    for row in inventory:
        sold_quantity = sold[row['cigar_id']]
        days_of_stock = None
        warning_type = None
        if sold_quantity == 0:
            warning_type = 'no_movement_90d'
        else:
            days_of_stock = (
                Decimal(row['quantity']) * Decimal('90') / Decimal(sold_quantity)
            ).quantize(MONEY)
            if days_of_stock > Decimal('180'):
                warning_type = 'overstock_180d'
        if warning_type:
            warnings.append({
                'cigar_id': row['cigar_id'],
                'name': f"{row['cigar__brand']} {row['cigar__name'] or row['cigar__english_name']}",
                'warning_type': warning_type,
                'inventory_cost_cny': _money(row['cost_cny']),
                'quantity': row['quantity'],
                'fulfilled_quantity_90d': sold_quantity,
                'estimated_days_of_stock': days_of_stock,
            })
    warnings.sort(key=lambda item: -item['inventory_cost_cny'])
    return {'status': 'available', 'reason': None, 'items': warnings[:5]}


def _inventory_facts(*, start, end, product_cost, is_current):
    day1_opening = _sum_category(
        LedgerPosting.Category.INVENTORY,
        start=start,
        end=end,
        transaction_type=LedgerTransaction.TransactionType.DAY1_OPENING,
    )
    opening = _money(
        _sum_category(LedgerPosting.Category.INVENTORY, end=start - timedelta(days=1))
        + day1_opening
    )
    closing = _money(_sum_category(LedgerPosting.Category.INVENTORY, end=end))
    received = _money(_sum_category(
        LedgerPosting.Category.INVENTORY,
        start=start,
        end=end,
        transaction_type=LedgerTransaction.TransactionType.PURCHASE_RECEIPT,
    ))
    adjustment = _money(_sum_category(
        LedgerPosting.Category.INVENTORY,
        start=start,
        end=end,
        transaction_type=LedgerTransaction.TransactionType.INVENTORY_ADJUSTMENT,
    ))
    average = _money((opening + closing) / Decimal('2'))
    turnover = (product_cost / average).quantize(RATE) if average > 0 else None
    return {
        'opening_cost_cny': opening,
        'received_cost_cny': received,
        'product_cost_consumed_cny': _money(product_cost),
        'adjustment_net_cny': adjustment,
        'closing_cost_cny': closing,
        'average_cost_cny': average,
        'monthly_turnover_rate': turnover,
        'warnings': _inventory_warnings(end=end, is_current=is_current),
    }


def _sales_facts(shipments, returns, net_revenue):
    fulfilled_revenue = sum(
        (shipment.sales_order.amount_due_cny for shipment in shipments),
        Decimal('0.00'),
    )
    return_reduction = sum(
        (returned.amount_cny for returned in returns), Decimal('0.00'),
    )
    return {
        'fulfilled_sales_revenue_cny': _money(fulfilled_revenue),
        'return_reduction_cny': _money(return_reduction),
        'net_sales_revenue_cny': _money(net_revenue),
        'fulfillment_order_count': len(shipments),
        'return_order_count': len(returns),
    }


def _period_facts(*, start, end, is_current, include_details):
    profit = _profit_facts(start=start, end=end)
    result = {
        'profit': profit,
        'metrics': {
            key: profit[key]
            for key in (
                'sales_revenue_cny', 'sales_profit_cny',
                'core_operating_profit_cny', 'net_operating_profit_cny',
            )
        },
    }
    if not include_details:
        return result
    rankings = _rankings(
        start=start, end=end, total_human_cost=profit['human_cost_cny'],
    )
    shipments = rankings.pop('_shipments')
    returns = rankings.pop('_returns')
    result.update({
        'sales': _sales_facts(shipments, returns, profit['sales_revenue_cny']),
        'cash': _cash_facts(start=start, end=end),
        'inventory': _inventory_facts(
            start=start,
            end=end,
            product_cost=profit['product_cost_cny'],
            is_current=is_current,
        ),
        'customers': _customer_summary(shipments, start=start, end=end),
        'rankings': rankings,
    })
    return result


def _comparison(current, previous, *, previous_start, previous_end, is_current):
    changes = {}
    for key, current_value in current['metrics'].items():
        previous_value = previous['metrics'][key]
        delta = _money(current_value - previous_value)
        if previous_value == 0:
            status = 'new' if current_value != 0 else 'not_available'
            change_rate = None
        else:
            status = 'available'
            change_rate = (delta / abs(previous_value)).quantize(RATE)
        changes[key] = {
            'current_cny': current_value,
            'previous_cny': previous_value,
            'delta_cny': delta,
            'change_rate': change_rate,
            'status': status,
        }
    return {
        'mode': 'same_days_previous_month' if is_current else 'full_previous_month',
        'previous_period_start': previous_start,
        'previous_period_end': previous_end,
        'metrics': changes,
    }


def _conclusions(report):
    profit = report['profit']
    comparison = report['comparison']['metrics']['sales_revenue_cny']
    cash = report['cash']
    inventory = report['inventory']
    conclusions = []
    if profit['sales_revenue_cny'] > 0:
        conclusions.append({
            'code': 'sales_margin',
            'status': 'available',
            'metric_keys': ['profit.sales_revenue_cny', 'profit.sales_profit_cny', 'profit.sales_profit_rate'],
            'text': '本月销售利润率已按销售收入、商品成本和人肉成本计算。',
        })
    else:
        conclusions.append({
            'code': 'sales_data_insufficient',
            'status': 'insufficient_data',
            'metric_keys': ['profit.sales_revenue_cny'],
            'text': '本期没有可用于销售利润分析的净销售收入。',
        })
    conclusions.append({
        'code': 'sales_comparison',
        'status': comparison['status'],
        'metric_keys': ['comparison.metrics.sales_revenue_cny'],
        'text': '净销售收入已按所选期间与上一月可比期间对照。',
    })
    conclusions.append({
        'code': 'working_capital',
        'status': 'attention' if cash['accounts_receivable_cny'] > 0 else 'available',
        'metric_keys': ['cash.accounts_receivable_cny', 'cash.customer_prepayments_cny'],
        'text': '期末应收款与客户预收款用于观察销售占款，不计入利润。',
    })
    if inventory['monthly_turnover_rate'] is not None:
        conclusions.append({
            'code': 'inventory_turnover',
            'status': 'available',
            'metric_keys': ['inventory.product_cost_consumed_cny', 'inventory.average_cost_cny', 'inventory.monthly_turnover_rate'],
            'text': '月度库存周转率由商品成本消耗除以月初月末平均库存成本。',
        })
    cost_rows = {
        'profit.product_cost_cny': profit['product_cost_cny'],
        'profit.human_cost_cny': profit['human_cost_cny'],
        'profit.operating_expenses_cny': profit['operating_expenses_cny'],
    }
    if any(cost_rows.values()):
        largest_key = max(cost_rows, key=cost_rows.get)
        conclusions.append({
            'code': 'largest_cost',
            'status': 'available',
            'metric_keys': [largest_key],
            'text': '成本结构中金额最高的项目已标记，便于继续查看明细。',
        })
    return conclusions[:5]


def monthly_business_report(*, month):
    period = _period(month)
    current = _period_facts(
        start=period['start'],
        end=period['end'],
        is_current=period['is_current'],
        include_details=True,
    )
    previous = _period_facts(
        start=period['previous_start'],
        end=period['previous_end'],
        is_current=False,
        include_details=False,
    )
    report = {
        'period': {
            'month': period['start'].strftime('%Y-%m'),
            'period_start': period['start'],
            'period_end': period['end'],
            'is_current_month': period['is_current'],
            'business_date_cutoff': period['end'],
        },
        **current,
        'comparison': _comparison(
            current,
            previous,
            previous_start=period['previous_start'],
            previous_end=period['previous_end'],
            is_current=period['is_current'],
        ),
    }
    report['conclusions'] = _conclusions(report)
    return report
