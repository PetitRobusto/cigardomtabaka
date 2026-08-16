import { createContext } from 'react';

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

export interface PageMeta {
  title: string;
  breadcrumbs: BreadcrumbItem[];
}

export interface PageMetaContextValue {
  meta: PageMeta;
  setMeta: (meta: PageMeta) => void;
}

// 页面元数据共享状态。
export const defaultMeta: PageMeta = {
  title: 'CigarDomTabaka',
  breadcrumbs: [],
};

export const PageMetaContext = createContext<PageMetaContextValue>({
  meta: defaultMeta,
  setMeta: () => {},
});
