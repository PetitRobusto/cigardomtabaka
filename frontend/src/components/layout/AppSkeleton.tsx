import { useEffect, useState } from 'react';
import { appSkeletonVariantForPath, type AppSkeletonVariant } from './appSections';

interface AppSkeletonProps {
  path?: string;
  variant?: AppSkeletonVariant;
  label?: string;
}

function Block({ className = '' }: { className?: string }) {
  return <span aria-hidden="true" className={`app-skeleton-block block ${className}`} />;
}

function SkeletonHeader() {
  return <div className="flex items-end justify-between gap-4">
    <div className="space-y-2"><Block className="h-8 w-44" /><Block className="h-3 w-64 max-w-[65vw]" /></div>
    <Block className="hidden h-9 w-24 sm:block" />
  </div>;
}

function CatalogSkeleton() {
  return <><SkeletonHeader /><div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
    {Array.from({ length: 10 }, (_, index) => <div key={index} className="rounded border border-border bg-white p-5">
      <Block className="mx-auto h-16 w-16 rounded-full" /><Block className="mx-auto mt-4 h-4 w-3/4" /><Block className="mx-auto mt-2 h-3 w-1/2" />
    </div>)}
  </div></>;
}

function TableSkeleton() {
  return <><SkeletonHeader />
    <div className="mt-6 grid grid-cols-2 overflow-hidden rounded border border-border bg-white lg:grid-cols-4">
      {Array.from({ length: 4 }, (_, index) => <div key={index} className="min-h-24 border-b border-r border-border p-4 lg:border-b-0 lg:last:border-r-0">
        <Block className="h-3 w-20" /><Block className="mt-3 h-7 w-28" /><Block className="mt-2 h-3 w-24" />
      </div>)}
    </div>
    <div className="mt-5 overflow-hidden rounded border border-border bg-white">
      <div className="flex gap-3 border-b border-border p-4"><Block className="h-9 flex-1" /><Block className="h-9 w-28" /></div>
      <div className="grid grid-cols-[1.2fr_2fr_1fr_1fr] gap-4 border-b border-border bg-[#FFFDFA] px-4 py-3">
        {Array.from({ length: 4 }, (_, index) => <Block key={index} className="h-3" />)}
      </div>
      {Array.from({ length: 5 }, (_, index) => <div key={index} className="grid grid-cols-[1.2fr_2fr_1fr_1fr] gap-4 border-b border-border px-4 py-3 last:border-0">
        <Block className="h-4" /><Block className="h-4" /><Block className="h-4" /><Block className="h-4" />
      </div>)}
    </div>
  </>;
}

function PanelSkeleton() {
  return <><SkeletonHeader /><div className="mt-6 grid gap-5 lg:grid-cols-[230px_minmax(0,1fr)]">
    <div className="rounded border border-border bg-white p-4 space-y-3">{Array.from({ length: 5 }, (_, index) => <Block key={index} className={`h-9 ${index === 0 ? 'w-full' : 'w-4/5'}`} />)}</div>
    <div className="rounded border border-border bg-white p-5"><Block className="h-6 w-48" /><Block className="mt-3 h-3 w-3/4" />
      <div className="mt-6 space-y-4">{Array.from({ length: 4 }, (_, index) => <div key={index} className="rounded border border-border p-4"><Block className="h-4 w-2/5" /><Block className="mt-3 h-3 w-full" /><Block className="mt-2 h-3 w-4/5" /></div>)}</div>
    </div>
  </div></>;
}

export function AppSkeleton({ path = '/', variant, label = '页面内容加载中…' }: AppSkeletonProps) {
  const resolvedVariant = variant ?? appSkeletonVariantForPath(path);
  return <section role="status" aria-live="polite" aria-busy="true" className="app-skeleton min-h-[420px] w-full animate-[app-skeleton-in_140ms_ease-out]">
    <span className="sr-only">{label}</span>
    {resolvedVariant === 'catalog' ? <CatalogSkeleton /> : resolvedVariant === 'table' ? <TableSkeleton /> : <PanelSkeleton />}
  </section>;
}

export function DelayedAppSkeleton({ path = '/', variant, label, delay = 140 }: AppSkeletonProps & { delay?: number }) {
  const [visiblePath, setVisiblePath] = useState<string | null>(delay === 0 ? path : null);
  useEffect(() => {
    if (delay === 0) return;
    const timer = window.setTimeout(() => setVisiblePath(path), delay);
    return () => window.clearTimeout(timer);
  }, [delay, path]);
  const visible = delay === 0 || visiblePath === path;

  return <div aria-busy="true" className="min-h-[420px] w-full">
    {visible ? <AppSkeleton path={path} variant={variant} label={label} /> : <span className="sr-only">{label ?? '页面内容加载中…'}</span>}
  </div>;
}
