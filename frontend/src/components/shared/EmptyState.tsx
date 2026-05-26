import { motion } from 'framer-motion';
import { Inbox } from 'lucide-react';

export function EmptyState({ title = '暂无数据', description = '等待数据抓取完成后自动显示' }: { title?: string; description?: string }) {
  return (
    <motion.div
      className="flex flex-col items-center justify-center py-20 text-center"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Inbox className="w-12 h-12 text-stone-400 mb-4" />
      <h3 className="text-stone-900 font-semibold text-lg mb-1">{title}</h3>
      <p className="text-stone-500 text-sm">{description}</p>
    </motion.div>
  );
}
