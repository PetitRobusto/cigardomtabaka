import { formatCny } from '../sales/salesState';

export function formatCostCny(value: string | number): string {
  return formatCny(Math.abs(Number(value)) || 0);
}
