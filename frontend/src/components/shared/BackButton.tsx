import { ArrowLeft } from 'lucide-react';

interface BackButtonProps {
  onClick: () => void;
}

export function BackButton({ onClick }: BackButtonProps) {
  return (
    <button
      onClick={onClick}
      className="group inline-flex items-center gap-2 px-4 py-2 border border-stone-200 rounded-sm text-stone-500 text-sm
        hover:bg-brand-tab-active hover:border-brand-brown hover:text-brand-brown transition-all duration-200 mb-5"
    >
      <ArrowLeft className="w-4 h-4 transition-transform duration-200 group-hover:-translate-x-0.5" />
      <span>返回</span>
    </button>
  );
}
