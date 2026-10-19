export type MobileNavItem = { kind: 'link'; to: string; label: string } | { kind: 'menu'; label: string };

export function mobileNavItems(isStaff: boolean, locale: 'zh-CN' | 'ru' | 'en' = 'zh-CN'): readonly MobileNavItem[] {
  const prefix = locale === 'zh-CN' ? '' : `/${locale}`;
  if (!isStaff) return [
    { kind: 'link', to: prefix ? `${prefix}/` : '/', label: locale === 'zh-CN' ? '品牌' : locale === 'ru' ? 'Каталог' : 'Catalogue' },
    { kind: 'link', to: `${prefix}/contacts`, label: locale === 'zh-CN' ? '到店与联系' : locale === 'ru' ? 'Контакты' : 'Contact' },
  ];
  return [
    { kind: 'link', to: '/', label: '品牌' },
    { kind: 'link', to: '/inventory', label: '库存' },
    { kind: 'link', to: '/sales', label: '订单' },
    { kind: 'link', to: '/accounting', label: '账务' },
    { kind: 'menu', label: '更多' },
  ];
}
