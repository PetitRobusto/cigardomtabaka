import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search, ChevronLeft, Cigarette } from 'lucide-react';
import { fetchBrandDetail } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import type { CigarSummary } from '../types';

const FILTER_OPTIONS = [
  { key: 'all', label: '全部' },
  { key: 'regular', label: '常规' },
  { key: 'limited', label: '限量' },
  { key: 'regional', label: '地区限定' },
];

export default function BrandDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['brand', slug],
    queryFn: () => fetchBrandDetail(slug!),
    enabled: !!slug,
  });

  if (isLoading) return <LoadingState text="加载品牌详情…" />;
  if (error) return <ErrorState message="数据加载失败" onRetry={() => refetch()} />;
  if (!data) return <EmptyState title="品牌不存在" />;

  const { brand, sections } = data;

  const getCigarType = (c: CigarSummary) => {
    const rt = c.release_type || '';
    if (rt.includes('Limited Edition')) return 'limited';
    if (rt.includes('Regional Edition')) return 'regional';
    if (rt) return 'other-special';
    return 'regular';
  };

  const filteredSections = sections.map(section => ({
    ...section,
    cigars: section.cigars.filter((c: CigarSummary) => {
      const type = getCigarType(c);
      const matchFilter = filter === 'all' || type === filter;
      const matchSearch = !search ||
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.english_name.toLowerCase().includes(search.toLowerCase());
      return matchFilter && matchSearch;
    }),
  })).filter(s => s.cigars.length > 0 || s.is_header);

  return (
    <div className="animate-fade-in">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-muted mb-6">
        <Link to="/" className="hover:text-accent transition-colors">所有品牌</Link>
        <span>/</span>
        <span className="text-fg">{brand.name}</span>
      </div>

      {/* Brand Hero */}
      <div className="flex items-start gap-4 mb-8">
        <div className="w-20 h-20 rounded-lg bg-accent-light flex items-center justify-center overflow-hidden shrink-0">
          {brand.logo_url ? (
            <img src={brand.logo_url} alt={brand.name} className="w-full h-full object-contain p-2" />
          ) : (
            <span className="font-display text-3xl text-accent font-semibold">{brand.name[0]}</span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="font-display text-2xl font-semibold text-fg">{brand.name}</h1>
          <div className="text-sm text-muted mt-0.5">{brand.english_name}</div>
          <div className="flex items-center gap-3 mt-2 text-xs text-muted">
            {brand.origin === 'Cuban' && <span className="text-accent">古巴 · 哈瓦那</span>}
            <span>{data.total} 款雪茄</span>
          </div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-6">
        <div className="relative max-w-xs w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
          <input
            type="text"
            placeholder="搜索雪茄名称…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent transition-all"
          />
        </div>
        <div className="flex items-center gap-1 ml-auto">
          {FILTER_OPTIONS.map(opt => (
            <button
              key={opt.key}
              onClick={() => setFilter(opt.key)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                filter === opt.key
                  ? 'bg-accent text-white'
                  : 'text-muted hover:text-fg hover:bg-white border border-border'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Cigar Grids */}
      {filteredSections.length === 0 ? (
        <EmptyState title="未找到匹配雪茄" description="请尝试其他搜索词或筛选条件" />
      ) : (
        <div className="space-y-6">
          {filteredSections.map((section, idx) => (
            <div key={idx}>
              {!section.is_header && (
                <h3 className="font-display text-base font-semibold text-fg mb-3">{section.label}</h3>
              )}
              {section.is_header && (
                <h3 className="font-display text-base font-semibold text-fg mt-4 mb-3">{section.label}</h3>
              )}
              {!section.is_header && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {section.cigars.map((cigar: CigarSummary) => {
                    const type = getCigarType(cigar);
                    return (
                      <Link
                        key={cigar.id}
                        to={`/cigar/${cigar.id}`}
                        className={`group bg-white border rounded-md overflow-hidden transition-all duration-200 hover:border-accent hover:shadow-md ${
                          type === 'limited' ? 'border-amber-200' :
                          type === 'regional' ? 'border-emerald-200' :
                          type === 'other-special' ? 'border-purple-200' :
                          'border-border'
                        }`}
                      >
                        <div className="p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-fg truncate">{cigar.name}</div>
                              {cigar.name !== cigar.english_name && (
                                <div className="text-xs text-muted truncate">{cigar.english_name}</div>
                              )}
                            </div>
                            {type === 'limited' && (
                              <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">限量</span>
                            )}
                            {type === 'regional' && (
                              <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">地限</span>
                            )}
                            {type === 'other-special' && (
                              <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">特别</span>
                            )}
                          </div>
                        </div>
                        {/* Image */}
                        <div className="aspect-[3/1] bg-accent-light/30 flex items-center justify-center overflow-hidden">
                          {cigar.thumb_url ? (
                            <img
                              src={cigar.thumb_url}
                              alt={cigar.name}
                              className="w-full h-full object-contain p-2"
                              loading="lazy"
                            />
                          ) : (
                            <Cigarette className="w-8 h-8 text-border" />
                          )}
                        </div>
                        <div className="px-3 py-2 flex items-center justify-between text-xs text-muted">
                          <span>
                            {cigar.length && cigar.ring_gauge
                              ? `${Math.round(cigar.length)}mm · ${Math.round(cigar.ring_gauge)}环径`
                              : cigar.vitola || ''}
                          </span>
                          {cigar.release_type_cn && (
                            <span className="truncate max-w-[120px]">{cigar.release_type_cn}</span>
                          )}
                        </div>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
