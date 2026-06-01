import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, Package, Boxes, Hash, DollarSign } from 'lucide-react';
import { fetchInventory } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import type { InventoryItem } from '../types';

export default function InventoryPage() {
  const [brandFilter, setBrandFilter] = useState('');
  const [search, setSearch] = useState('');

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['inventory', brandFilter, search],
    queryFn: () => fetchInventory({ brand: brandFilter, q: search }),
  });

  if (isLoading) return <LoadingState text="加载库存数据…" />;
  if (error) return <ErrorState message="数据加载失败" onRetry={() => refetch()} />;

  const stats = data?.stats;
  const cigars = data?.cigars || [];
  const brands = data?.brands || [];

  return (
    <div className="animate-fade-in">
      <h1 className="font-display text-2xl font-semibold text-fg mb-6">库存管理</h1>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
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
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        <select
          value={brandFilter}
          onChange={e => setBrandFilter(e.target.value)}
          className="px-3 py-2 bg-white border border-border rounded-md text-sm text-fg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent sm:w-48"
        >
          <option value="">全部品牌</option>
          {brands.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <input
            type="text"
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

      {/* Table / Cards */}
      {cigars.length === 0 ? (
        <EmptyState title={brandFilter || search ? "没有匹配的库存记录" : "暂无库存"} />
      ) : (
        <>
          {/* Desktop Table */}
          <div className="hidden lg:block bg-white border border-border rounded-md overflow-hidden">
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
