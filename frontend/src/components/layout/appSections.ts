export type AppSection = 'catalog' | 'inventory' | 'sales' | 'accounting' | 'prices' | 'privnote' | 'help';

export type AppSkeletonVariant = 'catalog' | 'table' | 'panel';

const SECTION_PREFIXES: ReadonlyArray<{ prefix: string; section: AppSection }> = [
  { prefix: '/inventory', section: 'inventory' },
  { prefix: '/sales', section: 'sales' },
  { prefix: '/accounting', section: 'accounting' },
  { prefix: '/prices', section: 'prices' },
  { prefix: '/privnote', section: 'privnote' },
  { prefix: '/p', section: 'privnote' },
  { prefix: '/help', section: 'help' },
];

const TABLE_SECTIONS = new Set<AppSection>(['inventory', 'sales', 'accounting', 'prices']);

/** Maps every nested URL to the top-level app whose navigation state it belongs to. */
export function appSectionForPath(pathname: string): AppSection {
  return SECTION_PREFIXES.find(({ prefix }) => pathname === prefix || pathname.startsWith(`${prefix}/`))?.section ?? 'catalog';
}

export function appSkeletonVariantForPath(pathname: string): AppSkeletonVariant {
  const section = appSectionForPath(pathname);
  if (section === 'catalog') return 'catalog';
  if (TABLE_SECTIONS.has(section)) return 'table';
  return 'panel';
}

export function isAppNavPathActive(pathname: string, target: string): boolean {
  if (target === '/') return appSectionForPath(pathname) === 'catalog';
  return pathname === target || pathname.startsWith(`${target}/`);
}
