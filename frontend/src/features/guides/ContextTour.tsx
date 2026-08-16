import { useEffect, useMemo, useRef, useState } from 'react';
import { canAdvanceTourStep, tourStepsForRoute } from './guideInteractions';
import { useLocation } from 'react-router-dom';
import type { GuideCompletionAction } from './guideInteractions';
import { shouldReuseTarget } from './targetTransition';
import { createMissingTargetReporter } from './missingTargetReporter';
import { FOCUSABLE_SELECTOR } from './focusables';
import { resolveTarget, restoreTarget } from './guideFocusController';

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
  const [seenTargetFor, setSeenTargetFor] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const targetRef = useRef<HTMLElement | null>(null);
  const step = steps[index];
  const targetSeen = seenTargetFor === step?.id;
  const focusInstruction = useMemo(() => step ? resolveTarget(step.target) : null, [step]);
  const closeRef = useRef<HTMLButtonElement>(null);
  const currentFocusInstruction = useRef(focusInstruction);
  useEffect(() => {
    // 在 effect 中同步最新目标，卸载时可恢复当前引导目标。
    currentFocusInstruction.current = focusInstruction;
  }, [focusInstruction]);

  useEffect(() => {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => {
      const opener = openerRef.current;
      const instruction = currentFocusInstruction.current;
      if (!instruction) return;
      const restored = restoreTarget(instruction.restoreId);
      if (restored.action === 'restore' && opener?.isConnected && !opener.hasAttribute('disabled')) opener.focus();
    };
  }, []);

  useEffect(() => {
    const missingTarget = createMissingTargetReporter(onMissingTarget);
    if (!step || !focusInstruction) { missingTarget.report(); return () => missingTarget.cancel(); }
    const updateTarget = () => {
      const nextTarget = document.querySelector<HTMLElement>(focusInstruction.selector);
      if (shouldReuseTarget(nextTarget, targetRef.current)) { setTargetFound(true); return; }
      targetRef.current?.classList.remove('guide-target-highlight');
      targetRef.current = nextTarget;
      if (!nextTarget) {
        setTargetFound(false);
        // 动态字段要等用户完成上一步（例如选中商品或保存草稿）才会出现。
        if (step.waitForTarget) missingTarget.cancel();
        else missingTarget.report();
        return;
      }
      missingTarget.cancel();
      setSeenTargetFor(step.id);
      nextTarget.classList.add('guide-target-highlight');
      if (focusInstruction.action === 'focus') nextTarget.focus();
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
  }, [focusInstruction, onMissingTarget, step]);

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

  if (!step || (!targetFound && !targetSeen && !step.waitForTarget)) return null;

  const next = () => index === steps.length - 1 ? onAction('finish') : setIndex(value => value + 1);
  return (
    <div className="fixed inset-0 z-[75] pointer-events-none" aria-hidden={false}>
      <div ref={dialogRef} className="pointer-events-auto fixed bottom-5 left-1/2 w-[min(390px,calc(100vw-2rem))] -translate-x-1/2 rounded-2xl border-2 border-accent bg-white p-5 shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="context-tour-title">
        <button ref={closeRef} type="button" aria-label="关闭页面引导" disabled={busy} onClick={() => onAction('close')} className="absolute right-3 top-3 rounded p-1 text-xl leading-none text-muted hover:bg-accent-light">×</button>
        <p className="text-[11px] font-bold uppercase tracking-[.15em] text-gold">页面引导 · {index + 1} / {steps.length}</p>
        <h2 id="context-tour-title" className="mt-2 font-display text-xl font-semibold">{step.title}</h2>
        <p className="mt-2 text-sm leading-6 text-muted">{step.description}</p>
        {!targetFound && !targetSeen && <p role="status" className="mt-3 rounded bg-gold/10 px-3 py-2 text-xs leading-5 text-fg">请先完成上一步，当前字段出现后再继续。</p>}
        {!targetFound && targetSeen && <p role="status" className="mt-3 rounded bg-green-50 px-3 py-2 text-xs leading-5 text-green-800">当前动作已完成，可以继续下一项。</p>}
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" disabled={busy} onClick={() => onAction('skip')} className="rounded px-3 py-2 text-sm text-muted hover:bg-accent-light">跳过</button>
          <button type="button" disabled={busy || index === 0} onClick={() => setIndex(value => Math.max(0, value - 1))} className="rounded border border-border px-3 py-2 text-sm disabled:opacity-40">← 上一项</button>
          <button type="button" disabled={busy || !canAdvanceTourStep(targetFound, targetSeen)} onClick={next} className="rounded bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{index === steps.length - 1 ? '完成' : '下一项 →'}</button>
        </div>
      </div>
    </div>
  );
}
