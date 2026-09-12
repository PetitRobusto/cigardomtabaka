import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

/** Native modal centers on the viewport and contains focus, including nested previews. */
export default function PaymentDialog({ title, onClose, busy = false, narrow = false, children }: {
  title: string; onClose: () => void; busy?: boolean; narrow?: boolean; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement;
    if (dialog.showModal) dialog.showModal(); else dialog.open = true;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      dialog.close?.();
      document.body.style.overflow = originalOverflow;
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);
  return createPortal(<dialog ref={ref} aria-label={title} aria-modal="true"
    onCancel={event => { event.preventDefault(); event.stopPropagation(); if (!busy) onClose(); }}
    onClick={event => { if (event.target === event.currentTarget && !busy) onClose(); }}
    className={`fixed inset-0 m-auto max-h-[100dvh] w-full overflow-y-auto rounded-lg border border-border bg-white p-0 text-fg shadow-2xl backdrop:bg-fg/40 sm:max-h-[calc(100dvh-2.5rem)] ${narrow ? 'sm:max-w-xl' : 'sm:w-[calc(100%-2.5rem)] sm:max-w-5xl'}`}>
    {children}
  </dialog>, document.body);
}
