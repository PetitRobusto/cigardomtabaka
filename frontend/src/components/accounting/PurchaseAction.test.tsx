import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import PurchaseAction, { selectActiveAccountId as selectPurchaseAccountId } from './PurchaseAction';

describe('采购动作卡 SSR 契约', () => {
  it('只提供草稿付款/取消和在途整单到货，展示 canonical 盒数', () => {
    const html = renderToStaticMarkup(<PurchaseAction {...({ purchases: [{ id: 10, status: 'draft', version: 1, items: [{ cigar_name: '测试雪茄', box_size: 25, box_quantity: 2, unit_price_rub_per_box: '25000.00' }] }, { id: 11, status: 'in_transit', version: 2, items: [{ cigar_name: '另一款雪茄', box_size: 10, box_quantity: 3, unit_price_rub_per_box: '12000.00' }] }], rubAccounts: [{ id: 3, name: '卢布银行卡', currency: 'RUB', is_active: true }], businessDate: '2026-08-15', onPay: () => undefined, onReceive: () => undefined, onCancel: () => undefined } as never)} />);
    expect(html).toContain('付款');
    expect(html).toContain('取消');
    expect(html).toContain('整单到货');
    expect(html).toContain('2');
    expect(html).toContain('盒');
    expect(html).not.toMatch(/分期|分批|部分到货|按件到货/);
  });

  it('box_quantity=null 且包装待复核时不渲染 0 盒', () => {
    const html = renderToStaticMarkup(<PurchaseAction {...({
      purchases: [{
        id: 12,
        status: 'draft',
        version: 1,
        items: [{ cigar_name: '待复核雪茄', box_size: 25, box_quantity: null, packaging_status: 'review_required', unit_price_rub_per_box: '25000.00' }],
      }],
      rubAccounts: [{ id: 3, name: '卢布银行卡', currency: 'RUB', is_active: true }],
      businessDate: '2026-08-15',
    } as never)} />);
    expect(html).not.toContain('0 盒');
    expect(html).toMatch(/待复核|—/);
  });

  it('stale 或非 active 的 RUB 账户 id 回退到当前合法账户', () => {
    const accounts = [
      { id: 3, name: '当前卢布银行卡', currency: 'RUB', is_active: true },
      { id: 4, name: '已停用卢布卡', currency: 'RUB', is_active: false },
    ];
    expect(selectPurchaseAccountId(accounts, 999)).toBe(3);
    expect(selectPurchaseAccountId(accounts, 4)).toBe(3);
    expect(selectPurchaseAccountId([], 999)).toBe('');
  });
});
