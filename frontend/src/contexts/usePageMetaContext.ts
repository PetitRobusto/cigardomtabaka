import { useContext } from 'react';
import { PageMetaContext } from './pageMetaStore';

// 读取当前页面元数据。
export function usePageMetaContext() {
  return useContext(PageMetaContext);
}
