import { useEffect, useRef, useState, type RefObject } from "react";

export function useStoreModal(ref: RefObject<HTMLDialogElement | null>) {
  const returnFocus = useRef<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = overflow; };
  }, [open]);
  const show = () => {
    returnFocus.current = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    setOpen(true);
  };
  const close = () => ref.current?.close();
  const onClose = () => { setOpen(false); returnFocus.current?.focus(); };
  const onBackdropClick = (event: React.MouseEvent<HTMLDialogElement>) => {
    if (event.target !== event.currentTarget) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close();
  };
  return { show, close, onClose, onBackdropClick };
}
