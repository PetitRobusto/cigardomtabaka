export type QuoteMode = 'full' | 'custom';

/** Keep an operator's explicit choices when the active custom-mode button is clicked again. */
export function selectedIdsOnCustomEntry(
  currentMode: QuoteMode,
  selectedIds: number[] | null,
): number[] | null {
  return currentMode === 'custom' ? selectedIds : null;
}
