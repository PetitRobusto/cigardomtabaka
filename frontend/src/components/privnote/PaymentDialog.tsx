import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

let openDialogs = 0;
let originalBodyOverflow = '';

/** Native modal centers on the viewport and contains focus, including nested previews. */
export default function PaymentDialog({ title, onClose, busy = false, width = '5xl', role, children }: {
  title: string; onClose: () => void; busy?: boolean; width?: 'md' | 'xl' | '3xl' | '5xl'; role?: 'alertdialog'; children: ReactNode;
}) {
  const widthClass = { md: 'max-w-md', xl: 'max-w-xl', '3xl': 'max-w-3xl', '5xl': 'max-w-5xl' }[width];
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement;
    if (dialog.showModal) dialog.showModal(); else dialog.open = true;
    if (openDialogs === 0) originalBodyOverflow = document.body.style.overflow;
    openDialogs += 1;
    document.body.style.overflow = 'hidden';
    return () => {
      dialog.close?.();
      openDialogs -= 1;
      if (openDialogs === 0) document.body.style.overflow = originalBodyOverflow;
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);
  return createPortal(<dialog ref={ref} role={role} aria-label={title} aria-modal="true"
    onCancel={event => { event.preventDefault(); event.stopPropagation(); if (!busy) onClose(); }}
    onClick={event => { if (event.target === event.currentTarget && !busy) onClose(); }}
    className={`fixed inset-0 m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] overflow-y-auto rounded-lg border border-border bg-white p-0 text-fg shadow-2xl backdrop:bg-fg/40 ${widthClass}`}>
    {children}
  </dialog>, document.body);
}
