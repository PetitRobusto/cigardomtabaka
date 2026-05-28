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
      <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mb-5">
        <AlertTriangle className="w-8 h-8 text-red-400" />
      </div>
      <p className="text-fg font-medium mb-5">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-accent text-white rounded-lg font-medium text-sm
            hover:bg-accent-hover active:scale-[0.98] transition-all duration-200 shadow-sm"
        >
          <RotateCcw className="w-4 h-4" />
          重新加载
        </button>
      )}
    </motion.div>
  );
}
