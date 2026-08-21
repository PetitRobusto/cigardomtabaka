import { NavLink } from 'react-router-dom';

const items = [
  { to: '/sales', label: '销售订单', end: true },
  { to: '/sales/customers', label: '客户管理', end: false },
];

export default function SalesSectionNav() {
  return <nav aria-label="订单应用导航" className="mb-5 flex w-fit rounded-md border border-border bg-white p-1 shadow-sm">
    {items.map(item => <NavLink
      key={item.to}
      to={item.to}
      end={item.end}
      className={({ isActive }) => `rounded px-4 py-2 text-xs font-semibold transition-colors ${isActive ? 'bg-accent text-white' : 'text-muted hover:bg-[#F5EFE8] hover:text-fg'}`}
    >{item.label}</NavLink>)}
  </nav>;
}
