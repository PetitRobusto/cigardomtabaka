import { motion } from 'framer-motion';

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
          className={`relative px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${
            days === d
              ? 'bg-gold-500 text-white shadow-sm'
              : 'bg-white text-stone-500 border border-stone-200 hover:border-gold-300 hover:text-gold-600'
          }`}
        >
          {days === d && (
            <motion.div
              layoutId="daysFilterActive"
              className="absolute inset-0 bg-gold-500 rounded-lg -z-10"
              transition={{ type: 'spring', bounce: 0.15, duration: 0.4 }}
            />
          )}
          {d}天
        </button>
      ))}
    </div>
  );
}
