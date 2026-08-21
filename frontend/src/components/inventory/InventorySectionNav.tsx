import { NavLink } from 'react-router-dom';
import { BUSINESS_STAFF_PATHS } from '../../pages/businessRoutes';

const items = [
  { to: BUSINESS_STAFF_PATHS.inventory, label: '现货库存', end: true },
  { to: BUSINESS_STAFF_PATHS.inventoryPurchases, label: '采购单', end: false },
];

export default function InventorySectionNav() {
  return <nav aria-label="库存子导航" className="mb-5 flex w-fit rounded-md border border-border bg-white p-1 shadow-sm">
    {items.map(item => <NavLink
      key={item.to}
      to={item.to}
      end={item.end}
      className={({ isActive }) => `rounded px-4 py-2 text-xs font-semibold transition-colors ${isActive ? 'bg-accent text-white' : 'text-muted hover:bg-[#F5EFE8] hover:text-fg'}`}
    >{item.label}</NavLink>)}
  </nav>;
}
