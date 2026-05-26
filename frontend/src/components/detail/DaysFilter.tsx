interface DaysFilterProps {
  days: number;
  onChange: (days: number) => void;
}

const OPTIONS = [7, 14, 30, 90];

export function DaysFilter({ days, onChange }: DaysFilterProps) {
  return (
    <div className="flex gap-2 mb-6">
      {OPTIONS.map((d) => (
        <button
          key={d}
          onClick={() => onChange(d)}
          className={`px-4 py-2 rounded-sm text-sm font-medium transition-all duration-200 ${
            days === d
              ? 'border-2 border-brand-brown bg-brand-tab-active text-brand-brown shadow-sm'
              : 'bg-white text-stone-700 border border-stone-200 hover:border-brand-brown hover:text-brand-brown'
          }`}
        >
          {d}天
        </button>
      ))}
    </div>
  );
}
