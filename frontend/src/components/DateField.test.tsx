// @vitest-environment jsdom
import { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import DateField from './DateField';

afterEach(cleanup);

it('表单日历遵守可选范围与必填状态，并在弹窗内优先响应 Escape', () => {
  const onChange = vi.fn();
  const onKeyDown = vi.fn();
  const { rerender } = render(<dialog open onKeyDown={onKeyDown}><DateField aria-label="业务日期"
    required min="2026-11-19" max="2026-11-24" value="2026-11-23" onChange={onChange} /></dialog>);
  const input = screen.getByLabelText('业务日期') as HTMLInputElement;
  fireEvent.click(input);
  const popup = document.querySelector('dialog .flatpickr-calendar.open')!;
  const outside = popup.querySelector<HTMLElement>('[aria-label="2026-11-25"]')!;
  fireEvent.click(outside);
  expect(onChange).not.toHaveBeenCalled();
  expect(input.value).toBe('2026-11-23');
  expect(screen.queryByText('清除日期')).toBeNull();
  fireEvent.keyDown(outside, { key: 'Escape' });
  expect(onKeyDown).not.toHaveBeenCalled();
  expect(popup.getAttribute('aria-hidden')).toBe('true');
  expect(document.activeElement).toBe(input);
  fireEvent.change(input, { target: { value: '2026-02-30' } });
  expect(input.value).toBe('');
  expect(input.checkValidity()).toBe(false);
  rerender(<dialog open><DateField aria-label="业务日期" disabled value="2026-11-20" onChange={onChange} /></dialog>);
  expect(document.querySelector('.flatpickr-calendar')).toBeNull();
  expect(input.value).toBe('2026-11-20');
});

it('筛选日期可以清空，外部修改会同步显示', () => {
  function Filter() {
    const [date, setDate] = useState('2026-11-23');
    return <><DateField aria-label="开始日期" value={date} onChange={e => setDate(e.target.value)} />
      <button onClick={() => setDate('2026-12-01')}>下个月</button><output>{date}</output></>;
  }
  render(<Filter />);
  const input = screen.getByLabelText('开始日期') as HTMLInputElement;
  fireEvent.click(input);
  fireEvent.click(screen.getByRole('button', { name: '清除日期' }));
  expect(input.value).toBe('');
  expect(screen.getByRole('status').textContent).toBe('');
  fireEvent.click(screen.getByText('下个月'));
  expect(input.value).toBe('2026-12-01');
});
