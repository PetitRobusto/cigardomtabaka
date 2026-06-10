import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { usePageMetaContext } from '../../contexts/PageMetaContext';

export default function Breadcrumb() {
  const { meta } = usePageMetaContext();

  if (meta.breadcrumbs.length === 0) return null;

  return (
    <nav className="py-3 mb-2">
      <ol className="flex items-center gap-1.5 text-[13px] text-muted flex-wrap">
        {meta.breadcrumbs.map((item, idx) => {
          const isLast = idx === meta.breadcrumbs.length - 1;
          return (
            <li key={idx} className="flex items-center gap-1.5">
              {idx > 0 && <ChevronRight className="w-3.5 h-3.5 text-border shrink-0" />}
              {isLast || !item.to ? (
                <span className={isLast ? 'text-fg font-medium' : ''}>{item.label}</span>
              ) : (
                <Link to={item.to} className="hover:text-accent transition-colors">
                  {item.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
