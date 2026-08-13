import { useEffect, useRef, useState } from 'react';
import { tourStepsForRoute } from './guideInteractions';
import { useLocation } from 'react-router-dom';
import type { GuideCompletionAction } from './guideInteractions';
import { createMissingTargetReporter } from './missingTargetReporter';
import { FOCUSABLE_SELECTOR } from './focusables';

interface Props {
  stepId?: string;
  onAction: (action: GuideCompletionAction) => void;
  onMissingTarget: () => void;
  busy?: boolean;
}

export default function ContextTour({ stepId, onAction, onMissingTarget, busy = false }: Props) {
  const location = useLocation();
  const steps = tourStepsForRoute(`${location.pathname}${location.hash}`, stepId);
  const initial = 0;
  const [index, setIndex] = useState(initial);
  const [targetFound, setTargetFound] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const targetRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const step = steps[index];

  useEffect(() => {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => {
      const opener = openerRef.current;
      if (opener?.isConnected && !opener.hasAttribute('disabled')) opener.focus();
    };
  }, []);

  useEffect(() => {
    const missingTarget = createMissingTargetReporter(onMissingTarget);
    if (!step) { missingTarget.report(); return () => missingTarget.cancel(); }
    const updateTarget = () => {
      const nextTarget = document.querySelector<HTMLElement>(step.target);
      if (nextTarget === targetRef.current) { setTargetFound(Boolean(nextTarget)); return; }
      targetRef.current?.classList.remove('guide-target-highlight');
      targetRef.current = nextTarget;
      if (!nextTarget) { setTargetFound(false); missingTarget.report(); return; }
      missingTarget.cancel();
      nextTarget.classList.add('guide-target-highlight');
      nextTarget.scrollIntoView({ behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
      setTargetFound(true);
    };
    updateTarget();
    const observer = typeof MutationObserver !== 'undefined' ? new MutationObserver(updateTarget) : null;
    observer?.observe(document.body, { childList: true, subtree: true });
    window.addEventListener('resize', updateTarget);
    window.addEventListener('scroll', updateTarget, { passive: true });
    return () => {
      observer?.disconnect();
      missingTarget.cancel();
      window.removeEventListener('resize', updateTarget);
      window.removeEventListener('scroll', updateTarget);
      targetRef.current?.classList.remove('guide-target-highlight');
    };
  }, [onMissingTarget, step]);

  useEffect(() => {
    if (!targetFound || !dialogRef.current) return;
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
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [targetFound]);

  if (!step || !targetFound) return null;

  const next = () => index === steps.length - 1 ? onAction('finish') : setIndex(value => value + 1);
  return (
    <div className="fixed inset-0 z-[75] pointer-events-none" aria-hidden={false}>
      <div ref={dialogRef} className="pointer-events-auto fixed bottom-5 left-1/2 w-[min(390px,calc(100vw-2rem))] -translate-x-1/2 rounded-2xl border-2 border-accent bg-white p-5 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="context-tour-title">
        <button ref={closeRef} type="button" aria-label="关闭页面引导" disabled={busy} onClick={() => onAction('close')} className="absolute right-3 top-3 rounded p-1 text-xl leading-none text-muted hover:bg-accent-light">×</button>
        <p className="text-[11px] font-bold uppercase tracking-[.15em] text-gold">页面引导 · {index + 1} / {steps.length}</p>
        <h2 id="context-tour-title" className="mt-2 font-display text-xl font-semibold">{step.title}</h2>
        <p className="mt-2 text-sm leading-6 text-muted">{step.description}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" disabled={busy} onClick={() => onAction('skip')} className="rounded px-3 py-2 text-sm text-muted hover:bg-accent-light">跳过</button>
          <button type="button" disabled={busy || index === 0} onClick={() => setIndex(value => Math.max(0, value - 1))} className="rounded border border-border px-3 py-2 text-sm disabled:opacity-40">← 上一项</button>
          <button type="button" disabled={busy} onClick={next} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white">{index === steps.length - 1 ? '完成' : '下一项 →'}</button>
        </div>
      </div>
    </div>
  );
}
