import { useRef } from 'react';
import { ChevronLeft, ChevronRight, Activity, Package } from 'lucide-react';
import { motion } from 'framer-motion';
import { RecentChangeCard } from './RecentChangeCard';
import type { RecentPriceChange, RecentRestock } from '../../types';

interface Props {
  priceChanges: RecentPriceChange[];
  restocks: RecentRestock[];
  onItemClick: (cigarId: number) => void;
}

function Section({
  title,
  icon: Icon,
  items,
  type,
  onItemClick,
}: {
  title: string;
  icon: React.ElementType;
  items: (RecentPriceChange | RecentRestock)[];
  type: 'price_change' | 'restock';
  onItemClick: (cigarId: number) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const scroll = (dir: 'left' | 'right') => {
    if (!scrollRef.current) return;
    const amount = 280;
    scrollRef.current.scrollBy({ left: dir === 'left' ? -amount : amount, behavior: 'smooth' });
  };

  if (items.length === 0) return null;

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-accent" />
          <h3 className="text-sm font-bold text-fg uppercase tracking-widest">{title}</h3>
          <span className="text-[0.7rem] text-muted">({items.length})</span>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => scroll('left')}
            className="p-1 rounded-md hover:bg-accent-light text-muted hover:text-accent transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => scroll('right')}
            className="p-1 rounded-md hover:bg-accent-light text-muted hover:text-accent transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
      <div
        ref={scrollRef}
        className="flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory scrollbar-hide"
        style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
      >
        {items.map((item, i) => (
          <motion.div
            key={`${type}-${item.cigar_id}-${item.source_slug}-${type === 'price_change' ? (item as RecentPriceChange).changed_at : (item as RecentRestock).restocked_at}`}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05, duration: 0.3 }}
            className="snap-start"
          >
            <RecentChangeCard
              item={item}
              type={type}
              onClick={() => onItemClick(item.cigar_id)}
            />
          </motion.div>
        ))}
      </div>
    </div>
  );
}

export function RecentChangesCarousel({ priceChanges, restocks, onItemClick }: Props) {
  if (priceChanges.length === 0 && restocks.length === 0) return null;

  return (
    <div className="mb-8">
      <Section
        title="近期价格变动"
        icon={Activity}
        items={priceChanges}
        type="price_change"
        onItemClick={onItemClick}
      />
      <Section
        title="近期补货"
        icon={Package}
        items={restocks}
        type="restock"
        onItemClick={onItemClick}
      />
    </div>
  );
}
