import catalog from './incomeCatalog.json';
import type { OtherIncomePayload } from '../../types';

interface IncomeItem {
  value: string;
  label: string;
  category: OtherIncomePayload['category'];
  notice: string;
  manual_entry_enabled: boolean;
  requires_recognition: boolean;
}
interface IncomeGroup { value: string; label: string; items: IncomeItem[] }

export const incomeGroups = catalog as IncomeGroup[];
const legacyLabels = { interest: '存款利息', used_item: '旧物出售', other: '其他收益' };
const legacyGroups = { interest: '利息与汇兑', used_item: '物品与资产处置', other: '其他收益' };

export function incomeClassification(payload: Pick<OtherIncomePayload, 'category' | 'subcategory'>) {
  for (const group of incomeGroups) {
    const item = group.items.find(item => item.value === payload.subcategory);
    if (item) return { group: group.label, item: item.label };
  }
  return { group: legacyGroups[payload.category], item: `${legacyLabels[payload.category]}（历史未细分）` };
}
