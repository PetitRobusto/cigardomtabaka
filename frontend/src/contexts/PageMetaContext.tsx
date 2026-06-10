import { createContext, useContext, useState, useCallback } from 'react';

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

interface PageMeta {
  title: string;
  breadcrumbs: BreadcrumbItem[];
}

interface PageMetaContextValue {
  meta: PageMeta;
  setMeta: (meta: PageMeta) => void;
}

const defaultMeta: PageMeta = {
  title: 'CigarDomTabaka',
  breadcrumbs: [],
};

const PageMetaContext = createContext<PageMetaContextValue>({
  meta: defaultMeta,
  setMeta: () => {},
});

export function PageMetaProvider({ children }: { children: React.ReactNode }) {
  const [meta, setMetaState] = useState<PageMeta>(defaultMeta);

  const setMeta = useCallback((newMeta: PageMeta) => {
    setMetaState(newMeta);
  }, []);

  return (
    <PageMetaContext.Provider value={{ meta, setMeta }}>
      {children}
    </PageMetaContext.Provider>
  );
}

export function usePageMetaContext() {
  return useContext(PageMetaContext);
}
