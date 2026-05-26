import { motion } from 'framer-motion';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({ message = '数据加载失败', onRetry }: ErrorStateProps) {
  return (
    <motion.div
      className="flex flex-col items-center justify-center py-20 text-center"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <AlertTriangle className="w-12 h-12 text-red-600 mb-4" />
      <p className="text-stone-900 mb-4">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-gold-500 text-white rounded-sm font-medium hover:bg-gold-600 transition-colors"
        >
          <RotateCcw className="w-4 h-4" />
          重新加载
        </button>
      )}
    </motion.div>
  );
}
