import { motion } from 'framer-motion';

interface StatsBarProps {
  snapshotCount: number;
  cigarCount: number;
  brandCount: number;
  sourceCount: number;
}

const items = [
  { key: 'snapshots', label: '价格条目' },
  { key: 'cigars', label: '雪茄款式' },
  { key: 'brands', label: '品牌覆盖' },
  { key: 'sources', label: '价格来源' },
] as const;

export function StatsBar({ snapshotCount, cigarCount, brandCount, sourceCount }: StatsBarProps) {
  const values: Record<string, number> = {
    snapshots: snapshotCount,
    cigars: cigarCount,
    brands: brandCount,
    sources: sourceCount,
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-7">
      {items.map((item, i) => (
        <motion.div
          key={item.key}
          className="bg-white rounded-md p-5 text-center border border-stone-100 shadow-sm hover:-translate-y-0.5 hover:shadow-md transition-all duration-200"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05, duration: 0.3 }}
        >
          <span className="block text-2xl md:text-[2rem] font-bold text-gold-500 leading-tight font-serif">
            {values[item.key]}
          </span>
          <span className="block text-xs text-stone-500 mt-1 uppercase tracking-wider">
            {item.label}
          </span>
        </motion.div>
      ))}
    </div>
  );
}
