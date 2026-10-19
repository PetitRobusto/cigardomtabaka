import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { usePageMeta } from '../hooks/usePageMeta';

export default function NotFoundPage() {
  const { setMeta } = usePageMeta();
  useEffect(() => { setMeta({ title: '页面不存在', breadcrumbs: [] }); }, [setMeta]);
  return <section><h1 className="font-display text-3xl">页面不存在</h1><p className="my-5 text-muted">请检查链接，或返回品牌目录。</p><Link to="/" className="text-accent underline">返回品牌目录</Link></section>;
}
