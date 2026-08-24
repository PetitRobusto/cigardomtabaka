export function autocompletePlacement(spaceAbove: number, spaceBelow: number, itemHeight = 52, minimumVisibleItems = 5): 'up' | 'down' {
  return spaceBelow < itemHeight * minimumVisibleItems && spaceAbove > spaceBelow ? 'up' : 'down';
}
