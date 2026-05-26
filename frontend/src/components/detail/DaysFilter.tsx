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
          className={`px-4 py-2 rounded-md text-sm font-semibold transition-all duration-200 ${
            days === d
              ? 'bg-[#A16207] text-white shadow-sm'
              : 'bg-white text-[#78716C] border border-[#E8E4DF] hover:border-[#A16207] hover:text-[#A16207]'
          }`}
        >
          {d}天
        </button>
      ))}
    </div>
  );
}
