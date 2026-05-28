import { ArrowLeft } from 'lucide-react';

interface BackButtonProps {
  onClick: () => void;
}

export function BackButton({ onClick }: BackButtonProps) {
  return (
    <button
      onClick={onClick}
      className="group inline-flex items-center gap-2 px-4 py-2.5 border border-border rounded-lg text-muted text-sm
        hover:bg-accent-light hover:border-accent hover:text-accent transition-all duration-200 mb-5
        focus:outline-none focus:ring-2 focus:ring-accent/30 focus:ring-offset-2 focus:ring-offset-cream"
    >
      <ArrowLeft className="w-4 h-4 transition-transform duration-200 group-hover:-translate-x-0.5" />
      <span>返回列表</span>
    </button>
  );
}
