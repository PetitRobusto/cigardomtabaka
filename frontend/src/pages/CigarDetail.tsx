import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchCigarDetail } from '../api';
import { usePriceHistory } from '../hooks/usePriceHistory';
import { useUIStore } from '../store/uiStore';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import { PageTransition } from '../components/animations/PageTransition';
import { usePageMeta } from '../hooks/usePageMeta';
import { ProductPlate } from '../components/detail/rebuild/ProductPlate';
import { IdentityCard } from '../components/detail/rebuild/IdentityCard';
import { AggregateBar } from '../components/detail/rebuild/AggregateBar';
import { OfferComparison } from '../components/detail/rebuild/OfferComparison';
import { PriceHistoryPanel } from '../components/detail/rebuild/PriceHistoryPanel';
import { statusOf, type OfferCounts } from '../components/detail/rebuild/detailFormatters';
import { average, eligibleVariant, unitPrice } from '../utils/offerPricing';

export default function CigarDetail() {
  const { id } = useParams<{ id: string }>();
  const { daysFilter, setDaysFilter } = useUIStore();
  const prices = usePriceHistory(id, daysFilter);
  const catalog = useQuery({ queryKey: ['cigar', id], queryFn: () => fetchCigarDetail(id!), enabled: !!id });
  const { setMeta } = usePageMeta();
  useEffect(() => {
    if (prices.data) setMeta({ title: `${prices.data.cigar_name} - 价格追踪` });
  }, [prices.data, setMeta]);

  if (prices.isLoading || catalog.isLoading) return <LoadingState text="加载雪茄详情…" />;
  if (prices.error) return <ErrorState message="价格数据加载失败，请刷新重试" onRetry={() => prices.refetch()} />;
  if (!prices.data) return <EmptyState title="暂无价格数据" description="该雪茄暂无价格记录" />;

  const variants = prices.data.variants;
  const active = variants.filter(eligibleVariant);
  const values = active.map(v => unitPrice(v.current_price_cny, v.box_size)!);
  const counts = variants.reduce<OfferCounts>((result, v) => {
    result[statusOf(v)] += 1;
    return result;
  }, { in: 0, out: 0, delisted: 0, invalid: 0 });
  const images = Object.values(catalog.data?.images_by_type || {}).flat();
  const last = variants.map(v => v.scraped_at).filter((value): value is string => !!value)
    .sort((a, b) => Date.parse(a) - Date.parse(b)).pop();
  const boxes = [...new Set(variants.map(v => v.box_label))].join(' / ') || '—';

  return (
    <PageTransition>
      <div className="rd-workspace">
        <nav className="rd-breadcrumb" aria-label="面包屑"><Link to="/prices">价格追踪</Link> / {prices.data.cigar_name}</nav>
        {catalog.error && <div className="rd-note mb-4">商品资料加载失败。<button onClick={() => catalog.refetch()} className="underline">重试资料</button></div>}
        <div className="rd-hero">
          <ProductPlate catalog={catalog.data} images={images} box={boxes} />
          <IdentityCard prices={prices.data} counts={counts} last={last ? new Date(last).toLocaleDateString('zh-CN') : '—'} />
        </div>
        <AggregateBar avg={average(values)} min={values.length ? Math.min(...values) : null} max={values.length ? Math.max(...values) : null} count={active.length} />
        <OfferComparison variants={variants} />
        <PriceHistoryPanel variants={variants} days={daysFilter} onDays={setDaysFilter} />
        <footer className="rd-footer">数据来源于各站点公开报价，仅供市场比较，不代表公司库存成本或会计入账金额。</footer>
      </div>
    </PageTransition>
  );
}
