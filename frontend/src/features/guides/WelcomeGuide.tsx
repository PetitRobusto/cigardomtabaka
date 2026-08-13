import { useEffect, useRef } from 'react';
import { GUIDE_STEPS } from './guideContent';
import type { GuideCompletionAction } from './guideInteractions';
import { FOCUSABLE_SELECTOR } from './focusables';

interface Props {
  stepIndex: number;
  onPrevious: () => void;
  onNext: () => void;
  onAction: (action: GuideCompletionAction) => void;
  busy?: boolean;
}

const POINTS = [
  ['资金余额', '业务总览'], ['库存价值', '库存与采购'], ['今日待办', '销售单'],
  ['确认出库', '出库与收款'], ['多币种账户', '账务与对账'], ['销售收入', '月度利润'],
];

export default function WelcomeGuide({ stepIndex, onPrevious, onNext, onAction, busy = false }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const step = GUIDE_STEPS[stepIndex] || GUIDE_STEPS[0];

  useEffect(() => {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (!focusable.length) return;
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      const opener = openerRef.current;
      if (opener?.isConnected && !opener.hasAttribute('disabled')) opener.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-fg/70 px-4 py-6" role="dialog" aria-modal="true" aria-labelledby="welcome-guide-title">
      <div ref={dialogRef} className="relative w-full max-w-2xl rounded-2xl border border-border bg-cream p-6 shadow-2xl sm:p-9">
        <button ref={closeRef} type="button" aria-label="关闭引导" disabled={busy} onClick={() => onAction('close')} className="absolute right-4 top-4 rounded p-2 text-xl leading-none text-muted hover:bg-accent-light hover:text-fg">×</button>
        <p className="text-[11px] font-bold uppercase tracking-[.15em] text-gold">欢迎加入 · 第 {stepIndex + 1} / {GUIDE_STEPS.length} 步</p>
        <div className="my-6 flex gap-1.5" aria-label={`${GUIDE_STEPS.length}步进度`}>
          {GUIDE_STEPS.map((item, index) => <i key={item.id} className={`h-1.5 flex-1 rounded-full ${index <= stepIndex ? 'bg-accent' : 'bg-border'}`} />)}
        </div>
        <h2 id="welcome-guide-title" className="font-display text-3xl font-semibold tracking-tight text-fg">{step.title}</h2>
        <p className="mt-3 max-w-xl text-sm leading-7 text-muted">{step.description}</p>
        <div className="my-7 grid gap-2 sm:grid-cols-3">
          {(POINTS[stepIndex] ? [POINTS[stepIndex]] : []).map(([point, label]) => <div key={point} className="rounded-xl bg-accent-light p-4"><b className="block text-lg text-fg">{point}</b><small className="text-muted">{label}</small></div>)}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
          <span className="text-xs text-muted">预计 2 分钟 · 可随时跳过</span>
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={() => onAction('skip')} className="rounded px-3 py-2 text-sm text-muted hover:bg-accent-light">跳过</button>
            <button type="button" disabled={busy || stepIndex === 0} onClick={onPrevious} className="rounded border border-border px-3 py-2 text-sm disabled:opacity-40">← 上一步</button>
            <button type="button" disabled={busy} onClick={stepIndex === GUIDE_STEPS.length - 1 ? () => onAction('finish') : onNext} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-hover">{stepIndex === GUIDE_STEPS.length - 1 ? '完成' : '下一步 →'}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
