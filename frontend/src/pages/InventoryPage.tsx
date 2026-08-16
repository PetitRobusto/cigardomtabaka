import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { fetchInventory, fetchInventoryAudit, reverseInventoryAdjustment, type InventoryAdjustmentSummary, type InventoryAuditResult } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import { usePageMeta } from '../hooks/usePageMeta';
import type { InventoryItem } from '../types';

export default function InventoryPage() {
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
    setMeta({
      title: '库存管理',
      breadcrumbs: [
        { label: '首页', to: '/' },
        { label: '库存管理' },
      ],
    });
  }, [setMeta]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['inventory', brandFilter, search],
    queryFn: () => fetchInventory({ brand: brandFilter, q: search }),
  });

  if (isLoading) return <LoadingState text="加载库存数据…" />;
  if (error) return <ErrorState message="数据加载失败" onRetry={() => refetch()} />;

  const stats = data?.stats;
  const cigars = data?.cigars || [];
  const brands = data?.brands || [];

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

  const inputForAdjustment = (item: InventoryAdjustmentSummary) => adjustmentInputs[item.id] || { businessDate: item.business_date, reason: '' };
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
    } catch (error) {
      setAdjustmentMessage(previous => ({ ...previous, [item.id]: error instanceof Error ? error.message : '撤销失败，请刷新后重试' }));
    } finally {
      setAdjustmentBusy(null);
    }
  };

  return (
    <div data-guide="inventory-summary" className="animate-fade-in">
      <h1 className="font-display text-2xl font-semibold text-fg mb-6">库存管理</h1>

      {/* Stats */}
      {stats && (
        <div data-guide="inventory-stats" className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          <div className="bg-white border border-border rounded-md p-4">
            <div className="text-xs text-muted uppercase tracking-wider mb-1">品牌</div>
            <div className="text-2xl font-bold text-fg">{stats.brand_count}</div>
          </div>
          <div className="bg-white border border-border rounded-md p-4">
            <div className="text-xs text-muted uppercase tracking-wider mb-1">款式</div>
            <div className="text-2xl font-bold text-fg">{stats.cigar_count}</div>
          </div>
          <div className="bg-white border border-border rounded-md p-4">
            <div className="text-xs text-muted uppercase tracking-wider mb-1">总库存</div>
            <div className="text-2xl font-bold text-accent">{stats.total_qty}<span className="text-sm font-normal text-muted ml-1">支</span></div>
          </div>
          <div className="bg-white border border-border rounded-md p-4">
            <div className="text-xs text-muted uppercase tracking-wider mb-1">总成本</div>
            <div className="text-2xl font-bold text-accent">¥{Math.round(stats.total_cost)}</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div data-guide="inventory-filters" className="flex flex-col sm:flex-row gap-3 mb-5">
        <select
          data-guide="inventory-brand-filter" value={brandFilter}
          onChange={e => setBrandFilter(e.target.value)}
          className="px-3 py-2 bg-white border border-border rounded-md text-sm text-fg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent sm:w-48"
        >
          <option value="">全部品牌</option>
          {brands.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <input
            data-guide="inventory-search" type="text"
            placeholder="搜索款式…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
          />
        </div>
        {(brandFilter || search) && (
          <button
            onClick={() => { setBrandFilter(''); setSearch(''); }}
            className="px-4 py-2 text-sm text-muted hover:text-accent border border-border rounded-md hover:bg-white transition-colors"
          >
            清除筛选
          </button>
        )}
      </div>

      <section data-guide="inventory-audit" className="mb-5 rounded-md border border-border bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h2 className="text-sm font-semibold text-fg">库存一致性审计</h2><p className="mt-1 text-xs text-muted">只读核对批次数量、成本和库存流水，不会自动修改数据。</p></div>
          <button data-guide="inventory-audit-run" type="button" onClick={runAudit} disabled={auditBusy} className="rounded border border-border px-3 py-2 text-sm text-fg hover:border-accent disabled:opacity-50">{auditBusy ? '审计中…' : '运行审计'}</button>
        </div>
        {auditError && <p role="alert" className="mt-3 text-sm text-red-700">{auditError}</p>}
        {audit && <div data-guide="inventory-audit-result" className={`mt-3 rounded px-3 py-2 text-sm ${audit.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`} role="status">{audit.ok ? '审计通过：库存数量和成本一致。' : `发现 ${audit.issue_count} 项问题，请先暂停相关出库并核对原始动作。`}{!audit.ok && audit.issues.length > 0 && <ul className="mt-2 list-disc pl-5 text-xs">{audit.issues.slice(0, 5).map((issue, index) => <li key={`${issue.batch_id ?? 'issue'}-${index}`}>{issue.message || issue.code || `批次 #${issue.batch_id ?? '—'}`}</li>)}</ul>}</div>}
        {audit?.recent_adjustments && audit.recent_adjustments.length > 0 && <div data-guide="inventory-adjustment-reversal" className="mt-4 border-t border-border pt-4"><h3 className="text-sm font-semibold text-fg">最近库存调整</h3><div className="mt-2 space-y-2">{audit.recent_adjustments.map(item => { const input = inputForAdjustment(item); const message = adjustmentMessage[item.id]; return <div key={item.id} className="rounded border border-border p-3"><div className="flex flex-wrap items-center justify-between gap-2 text-xs"><span className="font-medium">{item.cigar_name || `雪茄 #${item.cigar_id}`} · {item.quantity_delta > 0 ? '+' : ''}{item.quantity_delta} {item.inventory_form}</span><span className="text-muted">{item.business_date} · {item.reversed_at ? '已撤销' : item.can_reverse ? '可撤销' : '已有后续变化'}</span></div>{item.reason && <p className="mt-1 text-xs text-muted">原因为：{item.reason}</p>}{item.can_reverse && !item.reversed_at && <div className="mt-2 grid gap-2 sm:grid-cols-[150px_1fr_auto] sm:items-end"><label className="text-xs text-muted">撤销日期<input data-guide="inventory-adjustment-date" type="date" value={input.businessDate} onChange={event => setAdjustmentInputs(previous => ({ ...previous, [item.id]: { ...input, businessDate: event.target.value } }))} className="mt-1 block w-full rounded border border-border px-2 py-1.5 text-sm" /></label><label className="text-xs text-muted">撤销原因<input data-guide="inventory-adjustment-reason" value={input.reason} onChange={event => setAdjustmentInputs(previous => ({ ...previous, [item.id]: { ...input, reason: event.target.value } }))} className="mt-1 block w-full rounded border border-border px-2 py-1.5 text-sm" placeholder="说明为什么撤销" /></label><button data-guide="inventory-adjustment-submit" type="button" disabled={adjustmentBusy === item.id} onClick={() => void reverseAdjustment(item)} className="rounded border border-[#7A1F2E] px-3 py-1.5 text-sm text-[#7A1F2E] disabled:opacity-50">{adjustmentBusy === item.id ? '处理中…' : '撤销调整'}</button></div>}{message && <p className="mt-2 text-xs text-[#7A1F2E]">{message}</p>}</div>; })}</div></div>}
      </section>

      {/* Table / Cards */}
      {cigars.length === 0 ? (
        <EmptyState title={brandFilter || search ? "没有匹配的库存记录" : "暂无库存"} />
      ) : (
        <>
          {/* Desktop Table */}
          <div data-guide="inventory-table" className="hidden lg:block bg-white border border-border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[#F5EFE8] border-b border-border">
                  <th className="text-left px-4 py-3 font-medium text-muted">品牌</th>
                  <th className="text-left px-4 py-3 font-medium text-muted">款式</th>
                  <th className="text-right px-4 py-3 font-medium text-muted w-24">库存</th>
                  <th className="text-right px-4 py-3 font-medium text-muted w-28">成本均价</th>
                  <th className="text-right px-4 py-3 font-medium text-muted w-28">总成本</th>
                  <th className="text-right px-4 py-3 font-medium text-muted w-32">最近入库</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {cigars.map((c: InventoryItem) => (
                  <tr key={c.id} className="hover:bg-[#FAF8F5] transition-colors">
                    <td className="px-4 py-3 font-medium">{c.brand}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span>{c.name}</span>
                        {c.release_type_cn && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent text-white">{c.release_type_cn}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono">{c.total_stock}</td>
                    <td className="px-4 py-3 text-right font-mono">¥{c.avg_cost.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right font-mono">¥{Math.round(c.total_cost)}</td>
                    <td className="px-4 py-3 text-right text-xs text-muted">
                      {c.latest_date ? c.latest_date.slice(5, 10) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile Cards */}
          <div className="lg:hidden space-y-2">
            {cigars.map((c: InventoryItem) => (
              <div key={c.id} className="bg-white border border-border rounded-md p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs text-muted">{c.brand}</div>
                    <div className="text-sm font-medium text-fg flex items-center gap-1.5">
                      {c.name}
                      {c.release_type_cn && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent text-white">{c.release_type_cn}</span>
                      )}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-mono font-bold">{c.total_stock} <span className="text-xs font-normal text-muted">支</span></div>
                    <div className="text-xs text-muted">¥{Math.round(c.total_cost)}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
