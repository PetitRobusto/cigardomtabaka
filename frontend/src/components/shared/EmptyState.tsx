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
      <div className="w-16 h-16 rounded-2xl bg-accent-light flex items-center justify-center mb-5">
        <Inbox className="w-8 h-8 text-muted" />
      </div>
      <h3 className="text-fg font-semibold text-lg mb-1.5">{title}</h3>
      <p className="text-muted text-sm max-w-xs">{description}</p>
    </motion.div>
  );
}
