import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search, Cigarette } from 'lucide-react';
import { fetchBrandDetail } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import { usePageMeta } from '../hooks/usePageMeta';
import { generateCigarSlugFromParts } from '../utils/slug';
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
  const { setMeta } = usePageMeta();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['brand', slug],
    queryFn: () => fetchBrandDetail(slug!),
    enabled: !!slug,
  });

  useEffect(() => {
    if (data?.brand) {
      setMeta({
        title: data.brand.name,
        breadcrumbs: [
          { label: '首页', to: '/' },
          { label: data.brand.name },
        ],
      });
    }
  }, [data?.brand, setMeta]);

  if (isLoading) return <LoadingState text="加载品牌详情…" />;
  if (error) return <ErrorState message="数据加载失败" onRetry={() => refetch()} />;
  if (!data) return <EmptyState title="品牌不存在" />;

  const { brand, sections } = data;

  const getCigarType = (c: CigarSummary) => {
    const rt = c.release_type || '';
    if (rt.includes('Regional')) return 'regional';
    if (rt.includes('Limited') || rt.includes('Commemorative')) return 'limited';
    if (rt) return 'other-special';
    return 'regular';
  };

  const getBadgeInfo = (type: string) => {
    switch (type) {
      case 'regional': return { text: '地限', className: 'bg-accent text-white' };
      case 'limited': return { text: '限量', className: 'bg-accent-2 text-white' };
      case 'other-special': return { text: '特别', className: 'bg-muted text-white' };
      default: return null;
    }
  };

  const getBorderColor = (type: string) => {
    switch (type) {
      case 'regional': return 'border-l-accent';
      case 'limited': return 'border-l-accent-2';
      case 'other-special': return 'border-l-muted';
      default: return 'border-l-transparent';
    }
  };

  const filteredSections = sections.map(section => ({
    ...section,
    cigars: section.cigars.filter((c: CigarSummary) => {
      const type = getCigarType(c);
      let matchFilter = filter === 'all';
      if (filter === 'regular') matchFilter = type === 'regular';
      else if (filter === 'limited') matchFilter = type === 'limited' || type === 'other-special';
      else if (filter === 'regional') matchFilter = type === 'regional';
      const matchSearch = !search ||
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.english_name.toLowerCase().includes(search.toLowerCase());
      return matchFilter && matchSearch;
    }),
  })).filter(s => s.cigars.length > 0 || s.is_header);

  const totalVisible = filteredSections.reduce((sum, s) => sum + (s.is_header ? 0 : s.cigars.length), 0);

  return (
    <div className="animate-fade-in">
      {/* Brand Hero */}
      <div className="bg-white border border-border rounded p-6 sm:p-8 flex flex-col sm:flex-row gap-6 sm:gap-8 items-center sm:items-center mb-8">
        <div className="w-24 h-24 sm:w-[120px] sm:h-[120px] rounded bg-accent-3 flex items-center justify-center overflow-hidden shrink-0">
          {brand.logo_url ? (
            <img src={brand.logo_url} alt={brand.name} className="w-[80%] h-[80%] object-contain" />
          ) : (
            <span className="font-display text-5xl text-accent font-semibold">{brand.name[0]}</span>
          )}
        </div>
        <div className="flex-1 min-w-0 text-center sm:text-left">
          <h1 className="font-display text-[28px] font-semibold text-fg mb-1.5">{brand.name}</h1>
          <div className="font-display italic text-base text-muted mb-3">{brand.english_name}</div>
          <div className="flex flex-wrap items-center justify-center sm:justify-start gap-4 sm:gap-6 text-[13px] text-muted">
            {brand.origin === 'Cuban' && (
              <span><strong className="text-fg font-semibold">古巴</strong> · 哈瓦那</span>
            )}
            <span><strong className="text-fg font-semibold">{data.total}</strong> 款雪茄</span>
          </div>
        </div>
        <div className="flex gap-8 text-center shrink-0">
          <div>
            <span className="font-display text-[28px] font-semibold text-fg block leading-tight">{data.total}</span>
            <span className="text-[11px] text-muted uppercase tracking-[0.08em]">款雪茄</span>
          </div>
          <div>
            <span className="font-display text-[28px] font-semibold text-fg block leading-tight">
              {sections.filter(s => !s.is_header).length}
            </span>
            <span className="text-[11px] text-muted uppercase tracking-[0.08em]">系列</span>
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
            className="w-full pl-9 pr-4 py-2 bg-white border border-border rounded text-sm text-fg placeholder:text-muted focus:outline-none focus:border-accent transition-all"
          />
        </div>
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <span className="text-xs text-muted uppercase tracking-[0.08em] whitespace-nowrap">筛选</span>
          <div className="flex gap-1.5 flex-wrap">
            {FILTER_OPTIONS.map(opt => (
              <button
                key={opt.key}
                onClick={() => setFilter(opt.key)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all border ${
                  filter === opt.key
                    ? 'bg-accent text-white border-accent'
                    : 'bg-white text-fg border-border hover:border-accent hover:text-accent'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Cigar Grids */}
      {totalVisible === 0 ? (
        <EmptyState title="未找到匹配雪茄" description="请尝试其他搜索词或筛选条件" />
      ) : (
        <div className="space-y-6">
          {filteredSections.map((section, idx) => (
            <div key={idx}>
              {!section.is_header && (
                <h3 className="font-display text-base font-semibold text-fg mb-4">{section.label}</h3>
              )}
              {section.is_header && (
                <h3 className="font-display text-base font-semibold text-fg mt-6 mb-4">{section.label}</h3>
              )}
              {!section.is_header && (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                  {section.cigars.map((cigar: CigarSummary) => {
                    const type = getCigarType(cigar);
                    const badge = getBadgeInfo(type);
                    const borderLeft = getBorderColor(type);
                    return (
                      <Link
                        key={cigar.id}
                        to={`/cigar/${cigar.id}/${generateCigarSlugFromParts(brand.name, cigar.english_name, cigar.release_type)}`}
                        className={`group bg-white border border-border rounded overflow-hidden transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 border-l-[3px] ${borderLeft}`}
                      >
                        {/* Header */}
                        <div className="px-4 pt-4 pb-0 flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="text-[15px] font-semibold text-fg leading-tight">{cigar.name}</div>
                            {cigar.name !== cigar.english_name && (
                              <div className="font-display italic text-xs text-muted mt-0.5">{cigar.english_name}</div>
                            )}
                          </div>
                          {badge && (
                            <span className={`shrink-0 text-[10px] px-2 py-[3px] rounded font-semibold tracking-[0.05em] uppercase whitespace-nowrap ${badge.className}`}>
                              {badge.text}
                            </span>
                          )}
                        </div>
                        {/* Image */}
                        <div className="w-full aspect-[16/7] bg-accent-3 flex items-center justify-center overflow-hidden my-3">
                          {cigar.thumb_url ? (
                            <img
                              src={cigar.thumb_url}
                              alt={cigar.name}
                              className="w-[80%] h-auto max-h-full object-contain"
                              loading="lazy"
                            />
                          ) : (
                            <Cigarette className="w-8 h-8 text-border" />
                          )}
                        </div>
                        {/* Footer */}
                        <div className="px-4 pb-4 flex items-center justify-between gap-2">
                          <span className="text-xs text-muted">
                            {cigar.length && cigar.ring_gauge
                              ? `${Math.round(cigar.length)}mm · ${Math.round(cigar.ring_gauge)}环径`
                              : cigar.vitola || ''}
                          </span>
                          {cigar.release_type_cn && (
                            <span className="text-xs text-muted truncate max-w-[120px]">{cigar.release_type_cn}</span>
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
