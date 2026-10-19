export type MobileNavItem = { kind: 'link'; to: string; label: string } | { kind: 'menu'; label: string };

export function mobileNavItems(isStaff: boolean): readonly MobileNavItem[] {
  if (!isStaff) return [{ kind: 'link', to: '/', label: '品牌' }];
  return [
    { kind: 'link', to: '/', label: '品牌' },
    { kind: 'link', to: '/inventory', label: '库存' },
    { kind: 'link', to: '/sales', label: '订单' },
    { kind: 'link', to: '/accounting', label: '账务' },
    { kind: 'menu', label: '更多' },
  ];
}
