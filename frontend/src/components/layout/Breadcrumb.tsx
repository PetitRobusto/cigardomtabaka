import { Link, useLocation } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { usePageMetaContext } from '../../contexts/usePageMetaContext';
import { findPublicPage, localeHome, site } from '../../seo/metadata';

export default function Breadcrumb() {
  const { meta } = usePageMetaContext();
  const { pathname } = useLocation();
  const page = findPublicPage(pathname);
  // Public routes also render without effects during pre-rendering. Derive their
  // crumbs from the URL so a previous catalogue page cannot leak into contacts.
  const breadcrumbs = page
    ? page.kind === 'home' ? [] : [
      { label: site.locales[page.locale].catalog, to: localeHome(page.locale) },
      { label: page.title.replace(` · ${site.name}`, '') },
    ]
    : meta.breadcrumbs;

  if (breadcrumbs.length === 0) return null;

  return (
    <nav className="py-3 mb-2">
      <ol className="flex items-center gap-1.5 text-[13px] text-muted flex-wrap">
        {breadcrumbs.map((item, idx) => {
          const isLast = idx === breadcrumbs.length - 1;
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
