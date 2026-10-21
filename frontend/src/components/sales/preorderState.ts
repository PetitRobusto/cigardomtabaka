import type { PreorderSource, SalesOrder, SalesOrderPayload } from '../../types';
import { validateMoneyInput } from './salesState';

export interface PreorderSelection {
  selected: boolean;
  quantity: string;
  unitPrice: string;
}

export function preorderProductName(item: PreorderSource['items'][number]) {
  const brand = item.cigar_brand_cn || item.cigar_brand;
  return brand && !item.cigar_name.startsWith(brand) ? `${brand} ${item.cigar_name}` : item.cigar_name;
}

/** 类型标签只表达预售身份，履约进度交给状态标签。 */
export function salesPreorderLabel(order: SalesOrder): string | null {
  const items = order.items || [];
  const preorders = items.filter(item => item.fulfillment_type === 'preorder');
  if (!preorders.length) return null;
  return preorders.length === items.length ? '预售单' : '含预售';
}

export function salesPreorderStage(order: SalesOrder): string | null {
  const preorders = (order.items || []).filter(item => item.fulfillment_type === 'preorder');
  if (!preorders.length || order.fulfillment_status !== 'confirmed' || order.status === 'completed') return null;
  return preorders.every(item => item.preorder_reserved || item.preorder_prepared) ? '待出库'
      : preorders.some(item => item.preorder_reserved || item.preorder_prepared) ? '部分预留'
        : preorders.every(item => item.source_purchase_order_id) ? '待到货' : '待预留';
}

export function preorderUnitQuantity(item: PreorderSource['items'][number], sticks: number) {
  return item.sale_unit === 'box' ? Math.floor(sticks / (item.box_size || 1)) : sticks;
}

/** UI quantities are boxes/sticks; the API always receives normalized stick counts. */
export function preorderItems(source: PreorderSource, selections: PreorderSelection[]): SalesOrderPayload['items'] {
  if (!source.can_create) throw new Error('这张采购单当前不能创建预售单');
  const items = source.items.flatMap((item, index) => {
    const selection = selections[index];
    if (!selection?.selected) return [];
    const quantity = Number(selection.quantity);
    if (!Number.isSafeInteger(quantity) || quantity <= 0 || quantity > preorderUnitQuantity(item, item.remaining_quantity)) {
      throw new Error(`${item.cigar_name}：数量须为正整数，且不能超过剩余预售额度`);
    }
    if (!validateMoneyInput(selection.unitPrice)) throw new Error(`${item.cigar_name}：请填写非负、最多两位小数的人民币单价`);
    return [{
      cigar_id: item.cigar_id, fulfillment_type: 'preorder' as const,
      source_purchase_order_id: source.purchase_order_id, sale_unit: item.sale_unit,
      quantity: quantity * (item.sale_unit === 'box' ? item.box_size! : 1),
      sale_quantity: quantity, box_size: item.sale_unit === 'box' ? item.box_size! : undefined,
      unit_price: selection.unitPrice,
    }];
  });
  if (!items.length) throw new Error('请至少选择一款预售商品');
  return items;
}
