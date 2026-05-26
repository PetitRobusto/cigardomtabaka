import { motion, AnimatePresence } from 'framer-motion';
import { PriceCard } from './PriceCard';
import type { CigarGroup } from '../../types';

interface PriceCardGridProps {
  cigars: CigarGroup[];
  onCardClick: (cigarId: number) => void;
}

export function PriceCardGrid({ cigars, onCardClick }: PriceCardGridProps) {
  return (
    <motion.div
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
      layout
    >
      <AnimatePresence mode="popLayout">
        {cigars.map((cigar, i) => (
          <PriceCard
            key={cigar.cigar_id}
            cigar={cigar}
            index={i}
            onClick={() => onCardClick(cigar.cigar_id)}
          />
        ))}
      </AnimatePresence>
    </motion.div>
  );
}
