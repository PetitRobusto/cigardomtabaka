import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';
import { fetchBrandList } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import { usePageMeta } from '../hooks/usePageMeta';
import type { BrandItem } from '../types';

export default function BrandListPage() {
  const [search, setSearch] = useState('');
  const { setMeta } = usePageMeta();

  useEffect(() => {
    setMeta({
      title: '古巴雪茄目录',
      breadcrumbs: [{ label: '首页' }],
    });
  }, [setMeta]);

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
    <div data-guide="overview" className="animate-fade-in">
      {/* Page Header */}
        <div data-guide="overview-stats" className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-10">
        <div>
          <h1 className="font-display text-[32px] font-semibold text-fg tracking-tight leading-tight">古巴雪茄目录</h1>
          <p className="text-[13px] text-muted mt-1 uppercase tracking-[0.08em]">{data.total_brands} 个品牌 · 完整收录</p>
        </div>
        <div className="relative max-w-xs w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <input
            data-guide="overview-brand-search" type="text"
            placeholder="搜索品牌名称…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2.5 bg-white border border-border rounded text-sm text-fg placeholder:text-muted focus:outline-none focus:border-accent transition-all"
          />
        </div>
      </div>

      {/* Sections */}
      {filteredSections.length === 0 ? (
        <EmptyState title="未找到匹配品牌" description="请尝试其他搜索词" />
      ) : (
        <div data-guide="overview-brand-list" className="space-y-0">
          {filteredSections.map((section, sIdx) => (
            <div key={section.key}>
              {sIdx > 0 && <hr className="border-t border-border my-8" />}
              <section className="mb-12">
                <div className="flex items-center gap-3 mb-5">
                  <div className="w-5 h-0.5 bg-accent shrink-0" />
                  <h2 className="font-display text-lg font-semibold text-fg">{section.label}</h2>
                  <span className="text-[13px] text-muted ml-auto">
                    {section.brands.length} 个品牌
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                  {section.brands.map((brand: BrandItem) => (
                    <Link
                      key={brand.slug}
                      to={`/brand/${brand.slug}`}
                      className={`group bg-white border border-border rounded text-center p-6 pt-5 pb-4 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md ${
                        brand.category === 'discontinued' ? 'opacity-60 grayscale' : ''
                      }`}
                    >
                      <div className="w-20 h-20 mx-auto mb-4 rounded flex items-center justify-center overflow-hidden bg-accent-3">
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
                          <span className="font-display text-[28px] text-accent font-semibold">
                            {brand.name[0]}
                          </span>
                        )}
                      </div>
                      <div className="font-display text-base font-semibold text-fg mb-1">
                        {brand.name}
                      </div>
                      {brand.cigar_count > 0 && (
                        <div className="text-xs text-muted mb-3">{brand.cigar_count} 款雪茄</div>
                      )}
                      <div className="flex gap-1.5 justify-center flex-wrap">
                        {brand.origin === 'Cuban' && (
                          <span className="text-[11px] px-2.5 py-[3px] rounded-full bg-accent text-white font-medium border border-accent">
                            古巴
                          </span>
                        )}
                        {brand.category === 'global' && (
                          <span className="text-[11px] px-2.5 py-[3px] rounded-full bg-accent-3 text-accent-2 font-medium border border-[#E8DDD0]">
                            全球
                          </span>
                        )}
                        {brand.category === 'value' && (
                          <span className="text-[11px] px-2.5 py-[3px] rounded-full border border-border text-muted font-medium">
                            价值
                          </span>
                        )}
                        {brand.category === 'volume' && (
                          <span className="text-[11px] px-2.5 py-[3px] rounded-full border border-border text-muted font-medium">
                            走量
                          </span>
                        )}
                      </div>
                    </Link>
                  ))}
                </div>
              </section>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
