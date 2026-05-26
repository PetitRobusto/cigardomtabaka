import { motion, AnimatePresence } from 'framer-motion';
import { VariantCard } from './VariantCard';
import type { Variant } from '../../types';

interface VariantGridProps {
  variants: Variant[];
}

export function VariantGrid({ variants }: VariantGridProps) {
  return (
    <motion.div
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8"
      layout
    >
      <AnimatePresence mode="popLayout">
        {variants.map((v, i) => (
          <VariantCard key={`${v.source_slug}__${v.box_size}`} variant={v} index={i} />
        ))}
      </AnimatePresence>
    </motion.div>
  );
}
