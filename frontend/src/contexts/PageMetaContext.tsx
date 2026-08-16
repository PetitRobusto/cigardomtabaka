import { useState, useCallback } from 'react';
import { defaultMeta, PageMetaContext, type PageMeta } from './pageMetaStore';
export type { BreadcrumbItem } from './pageMetaStore';

export function PageMetaProvider({ children }: { children: React.ReactNode }) {
  const [meta, setMetaState] = useState(defaultMeta);

  const setMeta = useCallback((newMeta: PageMeta) => {
    setMetaState(newMeta);
  }, []);

  return (
    <PageMetaContext.Provider value={{ meta, setMeta }}>
      {children}
    </PageMetaContext.Provider>
  );
}
