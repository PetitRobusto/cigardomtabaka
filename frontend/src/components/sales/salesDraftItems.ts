import type { PreorderSource, SalesOrder, SalesOrderPayload, SearchCigarResult } from '../../types';
import { cigarSearchDisplayName } from '../../utils/cigarSearchDisplay';

export interface DraftProduct {
  cigarId: number;
  name: string;
  saleUnit: 'box' | 'stick';
  boxSize: string;
  quantity: string;
  unitPrice: string;
  fulfillmentType: 'in_stock' | 'preorder';
  sourceId?: number;
  sourceNumber?: string;
}

export function canEditDraft(order: SalesOrder): boolean {
  return order.fulfillment_status === 'draft' && order.payment_status === 'unpaid'
    && !order.locked && !order.items.some(item => item.allocations.length > 0);
}

export function draftProducts(order: SalesOrder): DraftProduct[] {
  return order.items.map(item => ({
    cigarId: item.cigar_id, name: item.cigar_name,
    saleUnit: item.sale_unit === 'box' ? 'box' : 'stick',
    boxSize: String(item.box_size ?? ''),
    quantity: String(item.sale_unit === 'box' ? item.sale_quantity : item.quantity),
    unitPrice: String(item.unit_price),
    fulfillmentType: item.fulfillment_type === 'preorder' ? 'preorder' : 'in_stock',
    sourceId: item.source_purchase_order_id ?? undefined,
    sourceNumber: item.source_purchase_order_number ?? undefined,
  }));
}

export function catalogProduct(cigar: SearchCigarResult): DraftProduct {
  const size = cigar.box_options[0]?.box_size ?? cigar.packaging_sizes[0];
  return { cigarId: cigar.id, name: cigarSearchDisplayName(cigar), saleUnit: size ? 'box' : 'stick',
    boxSize: size ? String(size) : '', quantity: '1', unitPrice: '', fulfillmentType: 'in_stock' };
}

export function sourceProduct(source: PreorderSource, item: PreorderSource['items'][number]): DraftProduct {
  return { cigarId: item.cigar_id, name: item.cigar_name, saleUnit: item.sale_unit,
    boxSize: String(item.box_size ?? ''), quantity: '1', unitPrice: '', fulfillmentType: 'preorder',
    sourceId: source.purchase_order_id, sourceNumber: source.order_number };
}

export function moneyCents(value: string): number | null {
  if (!/^\d+(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  return Number.isSafeInteger(cents) ? cents : null;
}

function positiveInteger(value: string): number | null {
  const parsed = Number(value);
  return /^\d+$/.test(value) && Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

export function draftGoodsCents(rows: DraftProduct[]): number | null {
  let total = 0;
  for (const row of rows) {
    const price = moneyCents(row.unitPrice);
    const count = positiveInteger(row.quantity);
    if (price === null || count === null) return null;
    total += price * count;
    if (!Number.isSafeInteger(total)) return null;
  }
  return total;
}

export function draftItemsPayload(order: SalesOrder, rows: DraftProduct[]): SalesOrderPayload {
  if (!canEditDraft(order)) throw new Error('当前订单不能编辑草稿');
  if (order.draft_revision == null) throw new Error('请重新打开草稿后编辑商品');
  if (!rows.length) throw new Error('至少保留一个商品');
  const items = rows.map((row, index) => {
    const count = positiveInteger(row.quantity);
    const size = row.saleUnit === 'box' ? positiveInteger(row.boxSize) : 1;
    if (count === null || size === null || !Number.isSafeInteger(count * size)) {
      throw new Error(`第 ${index + 1} 项：数量和盒规必须是正整数`);
    }
    const cents = moneyCents(row.unitPrice);
    if (cents === null) throw new Error(`第 ${index + 1} 项：请填写非负、最多两位小数的售价`);
    return { cigar_id: row.cigarId, sale_unit: row.saleUnit, quantity: count * size,
      sale_quantity: row.saleUnit === 'box' ? count : undefined,
      box_size: row.saleUnit === 'box' ? size : undefined,
      unit_price: (cents / 100).toFixed(2), fulfillment_type: row.fulfillmentType,
      source_purchase_order_id: row.fulfillmentType === 'preorder' ? row.sourceId : undefined };
  });
  if (draftGoodsCents(rows) === null) throw new Error('商品金额超出可保存范围');
  return { items, items_only: true, expected_revision: order.draft_revision };
}
