import { describe, expect, it } from 'vitest';
import type { FundAccount } from '../types';
import {
  PURCHASE_STATUS_FILTERS,
  buildPurchaseDraftPayload,
  canCancelPurchase,
  canEditPurchase,
  canReceivePurchase,
  canReverseReceivePurchase,
  purchaseActionMenu,
  purchaseStatusLabel,
  selectPurchaseRubAccountId,
} from './inventoryPurchases.logic';

describe('采购单工作台业务规则', () => {
  it('提供稳定的状态筛选和中文标签映射', () => {
    expect(PURCHASE_STATUS_FILTERS.map(filter => filter.value)).toEqual(['', 'draft', 'in_transit', 'received', 'cancelled']);
    expect(PURCHASE_STATUS_FILTERS.map(filter => filter.label)).toEqual(['全部订单', '草稿', '待到货', '已到货', '已取消']);
    expect(purchaseStatusLabel('draft')).toBe('草稿');
    expect(purchaseStatusLabel('in_transit')).toBe('待到货');
    expect(purchaseStatusLabel('received')).toBe('已到货');
    expect(purchaseStatusLabel('cancelled')).toBe('已取消');
    expect(purchaseStatusLabel('unknown')).toBe('unknown');
  });

  it('只允许草稿编辑/取消，待到货整单到货，已到货撤回', () => {
    expect(canEditPurchase('draft')).toBe(true);
    expect(canCancelPurchase('draft')).toBe(true);
    expect(canReceivePurchase('in_transit')).toBe(true);
    expect(canReverseReceivePurchase('received')).toBe(true);
    for (const status of ['in_transit', 'received', 'cancelled']) {
      expect(canEditPurchase(status)).toBe(false);
      expect(canCancelPurchase(status)).toBe(false);
    }
    expect(canReceivePurchase('draft')).toBe(false);
    expect(canReverseReceivePurchase('in_transit')).toBe(false);
  });

  it('将已到货撤回隔离在更多操作，而不是主操作区', () => {
    expect(purchaseActionMenu('draft')).toEqual({ primary: ['pay', 'edit', 'cancel'], more: [] });
    expect(purchaseActionMenu('in_transit')).toEqual({ primary: ['receive'], more: [] });
    expect(purchaseActionMenu('received')).toEqual({ primary: [], more: ['reverse_receive'] });
    expect(purchaseActionMenu('cancelled')).toEqual({ primary: [], more: [] });
  });

  it('构建草稿 payload 时保留不完整字段，不提前做付款校验', () => {
    expect(buildPurchaseDraftPayload({
      supplier_id: null,
      business_date: '',
      items: [{ cigar_id: 7, box_size: null, box_quantity: null, unit_price_rub_per_box: null }],
      note: null,
    })).toEqual({
      supplier_id: null,
      business_date: null,
      items: [{ cigar_id: 7, box_size: null, box_quantity: null, unit_price_rub_per_box: null }],
      note: '',
    });
  });

  it('付款账户只从启用 RUB 账户中选择', () => {
    const accounts = [
      { id: 2, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true },
      { id: 3, name: '卢布账户', currency: 'RUB', custodian_id: null, is_active: true },
      { id: 4, name: '停用卢布账户', currency: 'RUB', custodian_id: null, is_active: false },
    ] satisfies FundAccount[];
    expect(selectPurchaseRubAccountId(accounts, 3)).toBe(3);
    expect(selectPurchaseRubAccountId(accounts, 4)).toBe(3);
    expect(selectPurchaseRubAccountId(accounts, 999)).toBe(3);
    expect(selectPurchaseRubAccountId([], 3)).toBe('');
  });
});
