export function nextDay1DialogFocusIndex(currentIndex: number, focusableCount: number, reverse: boolean): number {
  if (focusableCount <= 0) return -1;
  return (currentIndex + (reverse ? -1 : 1) + focusableCount) % focusableCount;
}

export function day1DialogFocusIndexForActiveElement(currentIndex: number, focusableCount: number, reverse: boolean): number {
  // 从 aria-modal 外跳入时，按方向进入对应边界。
  return nextDay1DialogFocusIndex(currentIndex < 0 ? (reverse ? 0 : -1) : currentIndex, focusableCount, reverse);
}

export function createDay1DialogFocusController(dialog: HTMLElement, documentRef: Document = document) {
  const focusableControls = () => Array.from(dialog.querySelectorAll<HTMLElement>('button, input, select, textarea, a[href]'))
    .filter(element => !element.hasAttribute('disabled') && element.tabIndex !== -1);
  const handleTab = (event: KeyboardEvent) => {
    if (event.key !== 'Tab') return;
    const focusable = focusableControls();
    if (!focusable.length) return;
    const currentIndex = focusable.indexOf(documentRef.activeElement as HTMLElement);
    const nextIndex = day1DialogFocusIndexForActiveElement(currentIndex, focusable.length, event.shiftKey);
    event.preventDefault();
    focusable[nextIndex]?.focus();
  };
  const handleFocusIn = (event: FocusEvent) => {
    if (dialog.contains(event.target as Node)) return;
    focusableControls()[0]?.focus();
  };
  return {
    attach() {
      // 在 document 层捕获，避免 aria-modal 子树外泄漏焦点。
      documentRef.addEventListener('keydown', handleTab, true);
      documentRef.addEventListener('focusin', handleFocusIn, true);
      return () => {
        documentRef.removeEventListener('keydown', handleTab, true);
        documentRef.removeEventListener('focusin', handleFocusIn, true);
      };
    },
  };
}

export function restoreDay1DialogTriggerFocus(wasOpen: boolean, isOpen: boolean, trigger: () => HTMLElement | null, fallback?: () => HTMLElement | null): void {
  // 确认后触发按钮会卸载，退回聚焦冻结摘要。
  if (wasOpen && !isOpen) (trigger() || fallback?.())?.focus();
}
