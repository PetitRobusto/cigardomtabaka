import { motion } from 'framer-motion';
import { BarChart3, Flame, Tags, Globe } from 'lucide-react';

interface StatsBarProps {
  snapshotCount: number;
  cigarCount: number;
  brandCount: number;
  sourceCount: number;
}

const items = [
  { key: 'snapshots', label: '价格条目', icon: BarChart3 },
  { key: 'cigars', label: '雪茄款式', icon: Flame },
  { key: 'brands', label: '品牌覆盖', icon: Tags },
  { key: 'sources', label: '价格来源', icon: Globe },
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
      {items.map((item, i) => {
        const Icon = item.icon;
        return (
          <motion.div
            key={item.key}
            className="group bg-white rounded-xl p-5 border border-stone-100 shadow-sm
              hover:-translate-y-0.5 hover:shadow-md hover:border-gold-200
              transition-all duration-300"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05, duration: 0.3 }}
          >
            <div className="flex items-center gap-3 mb-2">
              <div className="w-8 h-8 rounded-lg bg-gold-50 flex items-center justify-center
                group-hover:bg-gold-100 transition-colors duration-300">
                <Icon className="w-4 h-4 text-gold-600" />
              </div>
              <span className="text-xs text-stone-400 uppercase tracking-wider font-medium">
                {item.label}
              </span>
            </div>
            <span className="block text-2xl md:text-[2rem] font-bold text-gold-500 leading-tight font-serif">
              {values[item.key]}
            </span>
          </motion.div>
        );
      })}
    </div>
  );
}
