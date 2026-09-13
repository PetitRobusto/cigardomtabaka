import type { HistoryRange } from '../../types';

const OPTIONS: { value: HistoryRange; label: string }[] = [
  { value: 30, label: '月' }, { value: 90, label: '3 个月' },
  { value: 180, label: '6 个月' }, { value: 365, label: '1 年' },
  { value: 'all', label: '全部' },
];

export function DaysFilter({ days, onChange }: { days: HistoryRange; onChange: (days: HistoryRange) => void }) {
  return (
    <div className="rd-chart-controls" role="group" aria-label="历史时间范围" data-guide="prices-history-filter">
      {OPTIONS.map(({ value, label }) => <button key={value} type="button" aria-pressed={days === value} onClick={() => onChange(value)}>{label}</button>)}
    </div>
  );
}
