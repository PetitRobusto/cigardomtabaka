import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { fetchInventory, fetchInventoryAudit, reverseInventoryAdjustment, type InventoryAdjustmentSummary, type InventoryAuditResult } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import InventorySectionNav from '../components/inventory/InventorySectionNav';
import { usePageMeta } from '../hooks/usePageMeta';
import type { InventoryItem, InventoryResponse } from '../types';
import { BRAND_LOGO_LOCAL } from '../utils/priceData';

export default function InventoryWorkbenchPage() {
  const [brandFilter, setBrandFilter] = useState('');
  const [search, setSearch] = useState('');
  const [audit, setAudit] = useState<InventoryAuditResult | null>(null);
  const [auditBusy, setAuditBusy] = useState(false);
  const [auditError, setAuditError] = useState('');
  const [adjustmentInputs, setAdjustmentInputs] = useState<Record<number, { businessDate: string; reason: string }>>({});
  const [adjustmentBusy, setAdjustmentBusy] = useState<number | null>(null);
  const [adjustmentMessage, setAdjustmentMessage] = useState<Record<number, string>>({});
  const { setMeta } = usePageMeta();

  useEffect(() => {
    setMeta({ title: '库存工作台', breadcrumbs: [{ label: '首页', to: '/' }, { label: '库存工作台' }] });
  }, [setMeta]);

  const inventory = useQuery({
    queryKey: ['inventory', brandFilter, search],
    queryFn: () => fetchInventory({ brand: brandFilter, q: search }),
  });

  if (inventory.isLoading) return <LoadingState text="加载库存数据…" />;
  if (inventory.error) return <ErrorState message="数据加载失败" onRetry={() => inventory.refetch()} />;

  const data = inventory.data;
  const cigars = data?.cigars || [];
  const brandOptions = data?.brand_options || data?.brands.map(brand => ({ key: brand, name: brand, logo_url: null })) || [];

  // 审计只读取库存事实；审计结果不会自动改动批次或流水。
  const runAudit = async () => {
    setAuditBusy(true);
    setAuditError('');
    try {
      setAudit(await fetchInventoryAudit());
    } catch {
      setAuditError('库存审计失败，请稍后重试');
    } finally {
      setAuditBusy(false);
    }
  };

  const inputForAdjustment = (item: InventoryAdjustmentSummary) => (
    adjustmentInputs[item.id] || { businessDate: item.business_date, reason: '' }
  );

  // 撤销保留原调整，并由后端创建对应的反向库存流水。
  const reverseAdjustment = async (item: InventoryAdjustmentSummary) => {
    const input = inputForAdjustment(item);
    if (!input.businessDate || !input.reason.trim()) {
      setAdjustmentMessage(previous => ({ ...previous, [item.id]: '撤销原因不能为空' }));
      return;
    }
    setAdjustmentBusy(item.id);
    setAdjustmentMessage(previous => ({ ...previous, [item.id]: '' }));
    try {
      await reverseInventoryAdjustment(item.id, { business_date: input.businessDate, reason: input.reason.trim() });
      setAdjustmentMessage(previous => ({ ...previous, [item.id]: '已提交撤销' }));
      await runAudit();
      await inventory.refetch();
    } catch (error) {
      setAdjustmentMessage(previous => ({
        ...previous,
        [item.id]: error instanceof Error ? error.message : '撤销失败，请刷新后重试',
      }));
    } finally {
      setAdjustmentBusy(null);
    }
  };

  return (
    <div data-guide="inventory-summary" className="w-full animate-fade-in">
      <InventorySectionNav />
      <header className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[.12em] text-accent">Inventory desk</p>
          <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">库存工作台</h1>
          <p className="mt-2 text-sm text-muted">查询现货数量与账面成本，必要时核对库存流水。</p>
        </div>
        <button type="button" onClick={() => inventory.refetch()} disabled={inventory.isFetching} className="inline-flex w-fit items-center gap-1 rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold disabled:opacity-50">
          <RefreshCw className={'h-4 w-4 ' + (inventory.isFetching ? 'animate-spin' : '')} />
          {inventory.isFetching ? '刷新中…' : '刷新'}
        </button>
      </header>

      {data?.stats && <InventoryStats data={data} />}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(680px,1fr)_340px]">
        <section className="min-w-0 overflow-hidden rounded-md border border-border bg-white shadow-sm">
          <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
            <div><h2 className="font-display text-lg font-semibold">现货库存</h2><p className="mt-0.5 text-xs text-muted">成本均价仅用于内部经营核对。</p></div>
            <span className="shrink-0 text-xs text-muted">显示 {cigars.length} 款</span>
          </div>
          <InventoryFilters brands={brandOptions} brandFilter={brandFilter} search={search} onBrandChange={setBrandFilter} onSearchChange={setSearch} onClear={() => { setBrandFilter(''); setSearch(''); }} />
          {cigars.length === 0
            ? <div className="px-5 py-10"><EmptyState title={brandFilter || search ? '没有匹配的库存记录' : '暂无库存'} /></div>
            : <InventoryList cigars={cigars} />}
        </section>

        <aside className="grid gap-4">
          <InventoryAuditPanel audit={audit} busy={auditBusy} error={auditError} onRun={() => void runAudit()} />
          {audit?.recent_adjustments && audit.recent_adjustments.length > 0 && (
            <InventoryAdjustmentsPanel
              items={audit.recent_adjustments}
              busyId={adjustmentBusy}
              messages={adjustmentMessage}
              inputFor={inputForAdjustment}
              onInputChange={(id, value) => setAdjustmentInputs(previous => ({ ...previous, [id]: value }))}
              onReverse={item => void reverseAdjustment(item)}
            />
          )}
        </aside>
      </div>
    </div>
  );
}

function InventoryStats({ data }: { data: InventoryResponse }) {
  const stats = data.stats;
  const cells = [
    { label: '库存品牌', value: String(stats.brand_count), note: '当前有货品牌' },
    { label: '库存款式', value: String(stats.cigar_count), note: '按雪茄款式合并' },
    { label: '现货总量', value: wholeNumber(stats.total_qty) + ' 支', note: '包含整盒与单支' },
    { label: '库存账面成本', value: '¥ ' + wholeNumber(stats.total_cost), note: '按实际采购批次汇总', accent: true },
  ];
  return (
    <section data-guide="inventory-stats" className="mb-7 grid grid-cols-2 overflow-hidden rounded-md border border-border bg-white shadow-sm lg:grid-cols-4">
      {cells.map((cell, index) => (
        <div key={cell.label} className={'min-h-24 p-4 lg:border-r lg:last:border-r-0 ' + (index < 2 ? 'border-b lg:border-b-0 ' : '') + (index % 2 === 0 ? 'border-r ' : '') + (cell.accent ? 'bg-[#FFFAF3]' : '')}>
          <p className="text-[11px] uppercase tracking-wider text-muted">{cell.label}</p>
          <p className={'mt-2 font-mono text-2xl font-semibold ' + (cell.accent ? 'text-accent' : 'text-fg')}>{cell.value}</p>
          <p className="mt-1 text-[11px] text-muted">{cell.note}</p>
        </div>
      ))}
    </section>
  );
}

function InventoryFilters({
  brands,
  brandFilter,
  search,
  onBrandChange,
  onSearchChange,
  onClear,
}: {
  brands: Array<{ key: string; name: string; logo_url: string | null }>;
  brandFilter: string;
  search: string;
  onBrandChange: (value: string) => void;
  onSearchChange: (value: string) => void;
  onClear: () => void;
}) {
  return (
    <div data-guide="inventory-filters" className="grid gap-2 border-b border-border bg-[#FFFDFA] p-4 sm:grid-cols-[190px_minmax(220px,1fr)_auto]">
      <select data-guide="inventory-brand-filter" value={brandFilter} onChange={event => onBrandChange(event.target.value)} className="rounded border border-border bg-white px-3 py-2 text-sm outline-none focus:border-gold">
        <option value="">全部品牌</option>
        {brands.map(brand => <option key={brand.key} value={brand.key}>{brand.name}</option>)}
      </select>
      <label className="relative">
        <span className="sr-only">搜索库存</span>
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted" />
        <input data-guide="inventory-search" value={search} onChange={event => onSearchChange(event.target.value)} placeholder="搜索品牌或款式" className="w-full rounded border border-border bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-gold" />
      </label>
      <button type="button" onClick={onClear} disabled={!brandFilter && !search} className="rounded border border-border bg-white px-3 py-2 text-sm hover:border-gold disabled:cursor-not-allowed disabled:opacity-40">清除筛选</button>
    </div>
  );
}

function InventoryList({ cigars }: { cigars: InventoryItem[] }) {
  const groups = Array.from(cigars.reduce((grouped, cigar) => {
    const key = cigar.brand;
    const current = grouped.get(key) || [];
    current.push(cigar);
    grouped.set(key, current);
    return grouped;
  }, new Map<string, InventoryItem[]>()).entries());

  const logoFor = (items: InventoryItem[]) => items[0]?.brand_logo_url || BRAND_LOGO_LOCAL[items[0]?.brand || ''] || null;
  const nameFor = (items: InventoryItem[]) => items[0]?.brand_name || items[0]?.brand || '未分类品牌';
  return (
    <>
      <div data-guide="inventory-table" className="hidden overflow-x-auto lg:block">
        <table className="w-full min-w-[720px] text-sm">
          <thead><tr className="bg-[#F5EFE8] text-xs text-muted"><th className="px-4 py-3 text-left font-medium">品牌与款式</th><th className="w-24 px-4 py-3 text-right font-medium">现货</th><th className="w-28 px-4 py-3 text-right font-medium">成本均价</th><th className="w-28 px-4 py-3 text-right font-medium">总成本</th><th className="w-28 px-4 py-3 text-right font-medium">最近入库</th></tr></thead>
          <tbody className="divide-y divide-border">
            {groups.map(([brand, items]) => <InventoryBrandGroup key={brand} items={items} logoUrl={logoFor(items)} brandName={nameFor(items)} />)}
          </tbody>
        </table>
        <div className="flex justify-between border-t border-border px-4 py-3 text-[11px] text-muted"><span>按最近入库排序</span><span>金额单位：人民币</span></div>
      </div>

      <div className="space-y-2 bg-cream p-3 lg:hidden">
        {groups.map(([brand, items]) => <section key={brand} className="overflow-hidden rounded-md border border-border bg-white"><BrandHeading brandName={nameFor(items)} logoUrl={logoFor(items)} count={items.length} /><div className="divide-y divide-border">{items.map(cigar => <article key={cigar.id} className="flex items-start justify-between gap-3 p-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-fg"><span>{cigar.name}</span>{cigar.release_type_cn && <span className="rounded-full bg-accent/10 px-1.5 py-0.5 text-[9px] text-accent">{cigar.release_type_cn}</span>}</div><p className="mt-1 text-xs text-muted">均价 ¥ {cigar.avg_cost.toFixed(2)}</p></div><div className="shrink-0 text-right font-mono"><p className="text-sm font-semibold text-accent">{wholeNumber(cigar.total_stock)} 支</p><p className="mt-1 text-xs text-muted">¥ {wholeNumber(cigar.total_cost)}</p></div></article>)}</div></section>)}
      </div>
    </>
  );
}

function BrandHeading({ brandName, logoUrl, count }: { brandName: string; logoUrl: string | null; count: number }) {
  return <div className="flex items-center gap-3 border-b border-border bg-[#FFFDFA] px-4 py-3"><div className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded border border-border bg-white">{logoUrl ? <img src={logoUrl} alt="" className="h-full w-full object-contain p-1" /> : <span className="font-display text-sm font-semibold text-accent">{brandName.slice(0, 1)}</span>}</div><div><h3 className="font-display text-base font-semibold text-fg">{brandName}</h3><p className="text-[11px] text-muted">{count} 款现货</p></div></div>;
}

function InventoryBrandGroup({ items, logoUrl, brandName }: { items: InventoryItem[]; logoUrl: string | null; brandName: string }) {
  return <>
    <tr className="bg-[#FFFDFA]"><td colSpan={5} className="px-4 py-3"><BrandHeading brandName={brandName} logoUrl={logoUrl} count={items.length} /></td></tr>
    {items.map(cigar => <tr key={cigar.id} className="transition-colors hover:bg-[#FFFAF6]"><td className="px-4 py-3 pl-8"><div className="flex items-center gap-2 font-medium text-fg"><span>{cigar.name}</span>{cigar.release_type_cn && <span className="rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] font-semibold text-accent">{cigar.release_type_cn}</span>}</div></td><td className="px-4 py-3 text-right font-mono font-semibold text-accent">{wholeNumber(cigar.total_stock)} 支</td><td className="px-4 py-3 text-right font-mono">¥ {cigar.avg_cost.toFixed(2)}</td><td className="px-4 py-3 text-right font-mono">¥ {wholeNumber(cigar.total_cost)}</td><td className="px-4 py-3 text-right text-xs text-muted">{shortDate(cigar.latest_date)}</td></tr>)}
  </>;
}

function InventoryAuditPanel({ audit, busy, error, onRun }: { audit: InventoryAuditResult | null; busy: boolean; error: string; onRun: () => void }) {
  return (
    <section data-guide="inventory-audit" className="rounded-md border border-border bg-white p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-accent/10 text-accent"><ShieldCheck className="h-5 w-5" /></span>
        <div><h2 className="font-display text-lg font-semibold">库存一致性</h2><p className="mt-1 text-xs leading-5 text-muted">只读核对批次数量、成本和库存流水，不会修改任何数据。</p></div>
      </div>
      {audit && (
        <div data-guide="inventory-audit-result" role="status" className={'mt-4 rounded-md px-3 py-2.5 text-sm ' + (audit.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800')}>
          <p>{audit.ok ? '审计通过：库存数量和成本一致。' : '发现 ' + audit.issue_count + ' 项问题，请先暂停相关出库。'}</p>
          {!audit.ok && audit.issues.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">{audit.issues.slice(0, 5).map((issue, index) => <li key={String(issue.batch_id ?? 'issue') + '-' + index}>{issue.message || issue.code || '批次 #' + (issue.batch_id ?? '—')}</li>)}</ul>}
        </div>
      )}
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <button data-guide="inventory-audit-run" type="button" onClick={onRun} disabled={busy} className="mt-4 w-full rounded border border-border bg-white px-3 py-2 text-sm font-medium hover:border-gold disabled:opacity-50">{busy ? '审计中…' : audit ? '重新运行审计' : '运行一致性审计'}</button>
    </section>
  );
}

function InventoryAdjustmentsPanel({
  items,
  busyId,
  messages,
  inputFor,
  onInputChange,
  onReverse,
}: {
  items: InventoryAdjustmentSummary[];
  busyId: number | null;
  messages: Record<number, string>;
  inputFor: (item: InventoryAdjustmentSummary) => { businessDate: string; reason: string };
  onInputChange: (id: number, value: { businessDate: string; reason: string }) => void;
  onReverse: (item: InventoryAdjustmentSummary) => void;
}) {
  return (
    <section data-guide="inventory-adjustment-reversal" className="rounded-md border border-border bg-white p-5 shadow-sm">
      <h2 className="font-display text-lg font-semibold">最近库存调整</h2>
      <p className="mt-1 text-xs leading-5 text-muted">撤销会保留原动作并写入反向流水。</p>
      <div className="mt-3 divide-y divide-border">
        {items.map(item => {
          const input = inputFor(item);
          const message = messages[item.id];
          return (
            <article key={item.id} className="py-3 first:pt-1 last:pb-0">
              <div className="flex items-start justify-between gap-2 text-xs">
                <span className="font-medium text-fg">{item.cigar_name || '雪茄 #' + item.cigar_id} · {item.quantity_delta > 0 ? '+' : ''}{item.quantity_delta} {item.inventory_form}</span>
                <span className={'shrink-0 ' + (item.can_reverse && !item.reversed_at ? 'text-accent' : 'text-muted')}>{item.reversed_at ? '已撤销' : item.can_reverse ? '可撤销' : '已有后续变化'}</span>
              </div>
              <p className="mt-1 text-[11px] text-muted">{item.business_date}{item.reason ? ' · ' + item.reason : ''}</p>
              {item.can_reverse && !item.reversed_at && (
                <div className="mt-3 grid gap-2">
                  <label className="text-xs text-muted">撤销日期<input data-guide="inventory-adjustment-date" type="date" value={input.businessDate} onChange={event => onInputChange(item.id, { ...input, businessDate: event.target.value })} className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm outline-none focus:border-gold" /></label>
                  <label className="text-xs text-muted">撤销原因<input data-guide="inventory-adjustment-reason" value={input.reason} onChange={event => onInputChange(item.id, { ...input, reason: event.target.value })} className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm outline-none focus:border-gold" placeholder="说明为什么撤销" /></label>
                  <button data-guide="inventory-adjustment-submit" type="button" disabled={busyId === item.id} onClick={() => onReverse(item)} className="rounded border border-accent px-3 py-1.5 text-sm text-accent hover:bg-accent/5 disabled:opacity-50">{busyId === item.id ? '处理中…' : '撤销调整'}</button>
                </div>
              )}
              {message && <p className="mt-2 text-xs text-accent">{message}</p>}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function wholeNumber(value: number): string {
  return Math.round(value).toLocaleString('zh-CN');
}

function shortDate(value: string | null): string {
  return value ? value.slice(5, 10) : '—';
}
