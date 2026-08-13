import { Link } from 'react-router-dom';
import { useEffect } from 'react';
import { usePageMeta } from '../hooks/usePageMeta';

export default function AccountingDay1Placeholder() {
  const { setMeta } = usePageMeta();
  useEffect(() => { setMeta({ title: '账务初始化', breadcrumbs: [{ label: '首页', to: '/' }, { label: '账务工作台', to: '/accounting' }, { label: '初始化' }] }); }, [setMeta]);
  return <section className="mx-auto max-w-2xl rounded-md border border-gold/40 bg-[#FFFAF3] p-6 shadow-sm">
    <p className="text-[11px] font-bold uppercase tracking-wider text-accent">Day 1</p>
    <h1 className="mt-2 font-display text-2xl font-semibold">账务初始化向导</h1>
    <p className="mt-3 text-sm leading-6 text-muted">初始化向导将在 Task 6 提供。当前入口已保留，尚未执行任何写入操作。</p>
    <Link to="/accounting" className="mt-5 inline-flex rounded bg-accent px-4 py-2 text-sm font-semibold text-white">返回账务工作台</Link>
  </section>;
}
