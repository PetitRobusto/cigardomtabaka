export function shouldReuseTarget(
  nextTarget: HTMLElement | null,
  currentTarget: HTMLElement | null,
): boolean {
  return nextTarget !== null && nextTarget === currentTarget;
}
