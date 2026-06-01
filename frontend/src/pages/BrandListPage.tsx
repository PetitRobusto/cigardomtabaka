import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Search, Cigarette } from 'lucide-react';
import { fetchBrandList } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import type { BrandItem } from '../types';

export default function BrandListPage() {
  const [search, setSearch] = useState('');
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['brands'],
    queryFn: fetchBrandList,
  });

  if (isLoading) return <LoadingState text="加载品牌数据…" />;
  if (error) return <ErrorState message="数据加载失败" onRetry={() => refetch()} />;
  if (!data || data.sections.length === 0) return <EmptyState title="暂无品牌数据" />;

  const filteredSections = data.sections.map(section => ({
    ...section,
    brands: section.brands.filter((b: BrandItem) =>
      !search || b.name.toLowerCase().includes(search.toLowerCase()) || b.english_name.toLowerCase().includes(search.toLowerCase())
    ),
  })).filter(s => s.brands.length > 0);

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl font-semibold text-fg tracking-tight">古巴雪茄目录</h1>
          <p className="text-muted text-sm mt-1">{data.total_brands} 个品牌 · 完整收录</p>
        </div>
        <div className="relative max-w-xs w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <input
            type="text"
            placeholder="搜索品牌名称…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent transition-all"
          />
        </div>
      </div>

      {/* Sections */}
      {filteredSections.length === 0 ? (
        <EmptyState title="未找到匹配品牌" description="请尝试其他搜索词" />
      ) : (
        <div className="space-y-8">
          {filteredSections.map(section => (
            <section key={section.key}>
              <div className="flex items-center gap-3 mb-4">
                <h2 className="text-lg font-semibold text-fg">{section.label}</h2>
                <span className="text-xs text-muted bg-white px-2 py-0.5 rounded-full border border-border">
                  {section.brands.length} 个品牌
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {section.brands.map((brand: BrandItem) => (
                  <Link
                    key={brand.slug}
                    to={`/brand/${brand.slug}`}
                    className={`group bg-white border border-border rounded-md p-4 transition-all duration-200 hover:border-accent hover:shadow-md ${
                      brand.category === 'discontinued' ? 'opacity-60 grayscale' : ''
                    }`}
                  >
                    <div className="flex flex-col items-center text-center gap-2">
                      <div className="w-14 h-14 rounded-md bg-accent-light flex items-center justify-center overflow-hidden">
                        {brand.logo_url ? (
                          <img
                            src={brand.logo_url}
                            alt={brand.name}
                            className="w-full h-full object-contain p-1"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = 'none';
                            }}
                          />
                        ) : (
                          <span className="font-display text-xl text-accent font-semibold">
                            {brand.name[0]}
                          </span>
                        )}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-fg leading-tight">{brand.name}</div>
                        {brand.cigar_count > 0 && (
                          <div className="text-xs text-muted mt-0.5">{brand.cigar_count} 款雪茄</div>
                        )}
                      </div>
                      <div className="flex gap-1">
                        {brand.origin === 'Cuban' && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent text-white">古巴</span>
                        )}
                        {brand.category === 'global' && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gold text-white">全球</span>
                        )}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
