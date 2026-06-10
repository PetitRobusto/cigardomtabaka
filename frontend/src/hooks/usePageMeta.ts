import { useCallback } from 'react';
import { usePageMetaContext, type BreadcrumbItem } from '../contexts/PageMetaContext';

interface PageMetaOptions {
  title: string;
  breadcrumbs?: BreadcrumbItem[];
}

export function usePageMeta() {
  const { meta, setMeta: setMetaRaw } = usePageMetaContext();

  const setMeta = useCallback((opts: PageMetaOptions) => {
    const fullTitle = opts.title ? `${opts.title} · CigarDomTabaka` : 'CigarDomTabaka';
    setMetaRaw({
      title: fullTitle,
      breadcrumbs: opts.breadcrumbs || [],
    });
  }, [setMetaRaw]);

  return { meta, setMeta };
}
