import { motion } from 'framer-motion';

export function LoadingState({ text = '加载中…' }: { text?: string }) {
  return (
    <motion.div
      className="flex flex-col items-center justify-center py-20"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <div className="w-10 h-10 rounded-full border-[3px] border-stone-200 border-t-gold-500 animate-spin" />
      <p className="mt-4 text-stone-500 text-sm">{text}</p>
    </motion.div>
  );
}
