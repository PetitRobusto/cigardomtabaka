import type { ComponentProps } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { FundAccount } from '../../types';
import PurchaseAction from './PurchaseAction';
import { selectActiveAccountId as selectPurchaseAccountId } from './PurchaseAction.logic';

describe('采购动作卡 SSR 契约', () => {
  it('只提供草稿付款/取消和在途整单到货，展示 canonical 盒数', () => {
    const props = {
      purchases: [
        {
          id: 10,
          status: 'draft',
          version: 1,
          items: [{ cigar_id: 101, cigar_name: '测试雪茄', box_size: 25, box_quantity: 2, unit_price_rub_per_box: '25000.00' }],
        },
        {
          id: 11,
          status: 'in_transit',
          version: 2,
          items: [{ cigar_id: 102, cigar_name: '另一款雪茄', box_size: 10, box_quantity: 3, unit_price_rub_per_box: '12000.00' }],
        },
      ],
      rubAccounts: [{ id: 3, name: '卢布银行卡', currency: 'RUB', custodian_id: null, is_active: true }],
      businessDate: '2026-08-15',
      onPay: () => undefined,
      onReceive: () => undefined,
      onCancel: () => undefined,
    } satisfies ComponentProps<typeof PurchaseAction>;
    const html = renderToStaticMarkup(<PurchaseAction {...props} />);
    expect(html).toContain('付款');
    expect(html).toContain('取消');
    expect(html).toContain('整单到货');
    expect(html).toContain('2');
    expect(html).toContain('盒');
    expect(html).not.toMatch(/分期|分批|部分到货|按件到货/);
  });

  it('box_quantity=null 且包装待复核时不渲染 0 盒', () => {
    const props = {
      purchases: [{
        id: 12,
        status: 'draft',
        version: 1,
        items: [{ cigar_id: 103, cigar_name: '待复核雪茄', box_size: 25, box_quantity: null, packaging_status: 'review_required', unit_price_rub_per_box: '25000.00' }],
      }],
      rubAccounts: [{ id: 3, name: '卢布银行卡', currency: 'RUB', custodian_id: null, is_active: true }],
      businessDate: '2026-08-15',
    } satisfies ComponentProps<typeof PurchaseAction>;
    const html = renderToStaticMarkup(<PurchaseAction {...props} />);
    expect(html).not.toContain('0 盒');
    expect(html).toMatch(/待复核|—/);
  });

  it('已到货采购单默认隐藏撤销表单，只显示危险操作展开入口', () => {
    const props = {
      purchases: [{
        id: 13,
        status: 'received',
        version: 3,
        items: [{ cigar_id: 104, cigar_name: '已到货雪茄', box_size: 25, box_quantity: 1, unit_price_rub_per_box: '25000.00' }],
      }],
      rubAccounts: [],
      businessDate: '2026-08-15',
      onReverseReceive: () => undefined,
    } satisfies ComponentProps<typeof PurchaseAction>;
    const html = renderToStaticMarkup(<PurchaseAction {...props} />);
    expect(html).toContain('显示撤销到货');
    expect(html).toMatch(/data-guide="accounting-purchase-reverse-reveal"/);
    expect(html).not.toContain('撤销原因');
    expect(html).not.toMatch(/data-guide="accounting-purchase-reverse-date"/);
    expect(html).not.toMatch(/data-guide="accounting-purchase-reverse-reason"/);
    expect(html).not.toMatch(/data-guide="accounting-purchase-reverse-submit"/);
  });

  it('stale 或非 active 的 RUB 账户 id 回退到当前合法账户', () => {
    const accounts = [
      { id: 3, name: '当前卢布银行卡', currency: 'RUB', custodian_id: null, is_active: true },
      { id: 4, name: '已停用卢布卡', currency: 'RUB', custodian_id: null, is_active: false },
    ] satisfies FundAccount[];
    expect(selectPurchaseAccountId(accounts, 999)).toBe(3);
    expect(selectPurchaseAccountId(accounts, 4)).toBe(3);
    expect(selectPurchaseAccountId([], 999)).toBe('');
  });
});
