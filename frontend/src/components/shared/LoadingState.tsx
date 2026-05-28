import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';

export function LoadingState({ text = '加载中…' }: { text?: string }) {
  return (
    <motion.div
      className="flex flex-col items-center justify-center py-20"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="relative w-12 h-12 mb-5">
        <div className="absolute inset-0 rounded-full border-2 border-border" />
        <div className="absolute inset-0 rounded-full border-2 border-accent border-t-transparent animate-spin" />
      </div>
      <p className="text-muted text-sm font-medium">{text}</p>
    </motion.div>
  );
}
