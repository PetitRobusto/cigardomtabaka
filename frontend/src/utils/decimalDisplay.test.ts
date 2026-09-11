import { describe, expect, it } from 'vitest';
import { formatDecimalAmount, formatDecimalRatio } from './decimalDisplay';

describe('财务 Decimal 字符串展示', () => {
  it('不经过 JS number，保留大额 USDT 的八位精度', () => {
    expect(formatDecimalAmount('999999999.12345678', 'USDT')).toBe('999,999,999.12345678');
    expect(formatDecimalAmount('-999999999.12345678', 'USDT', true)).toBe('999,999,999.12345678');
  });

  it('用整数运算计算并四舍五入实际汇率', () => {
    expect(formatDecimalRatio('1200.00', '100.00')).toBe('12.0000');
    expect(formatDecimalRatio('1.00', '3.00')).toBe('0.3333');
  });
});
