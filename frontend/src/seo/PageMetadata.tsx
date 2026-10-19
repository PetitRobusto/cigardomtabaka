import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { usePageMetaContext } from '../contexts/usePageMetaContext';
import { updateDocumentMetadata } from './metadata';

export function PageMetadata() {
  const { pathname } = useLocation();
  const { meta } = usePageMetaContext();
  useEffect(() => { updateDocumentMetadata(pathname, meta.title); }, [pathname, meta.title]);
  return null;
}
