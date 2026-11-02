import { describe, expect, it } from 'vitest';
import { otherIncomeCny } from './otherIncome';

describe('其他收入人民币预览', () => {
  it('用收入汇率除原币，按分四舍五入，不使用浮点或旧平均成本', () => {
    expect(otherIncomeCny('11000.00', 'RUB', '11')).toBe('1000.00');
    expect(otherIncomeCny('1', 'RUB', '8')).toBe('0.13');
    expect(otherIncomeCny('0.29', 'CNY')).toBe('0.29');
    expect(otherIncomeCny('999999999999.99', 'RUB', '10')).toBe('100000000000.00');
    expect(otherIncomeCny('1', 'RUB', '0.00000001')).toBe('100000000.00');
  });
  it('拒绝非法精度、零、负数、溢出和不到一分的结果', () => {
    for (const amount of ['', '0', '-1', '0.001', '1e2', 'NaN', '1000000000000', '1'.repeat(1000)]) {
      expect(otherIncomeCny(amount, 'CNY')).toBeNull();
    }
    for (const rate of ['', '0', '-1', '1.000000001', '10000000000', 'Infinity']) {
      expect(otherIncomeCny('1', 'RUB', rate)).toBeNull();
    }
    expect(otherIncomeCny('0.01', 'RUB', '12')).toBeNull();
    expect(otherIncomeCny('999999999999.99', 'RUB', '0.01')).toBeNull();
  });
});
