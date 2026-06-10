import { useParams, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { usePriceHistory } from '../hooks/usePriceHistory';
import { useUIStore } from '../store/uiStore';
import { BackButton } from '../components/shared/BackButton';
import { DetailHeader } from '../components/detail/DetailHeader';
import { VariantGrid } from '../components/detail/VariantGrid';
import { DaysFilter } from '../components/detail/DaysFilter';
import { PriceChart } from '../components/detail/PriceChart';
import { LoadingState } from '../components/shared/LoadingState';
import { EmptyState } from '../components/shared/EmptyState';
import { ErrorState } from '../components/shared/ErrorState';
import { PageTransition } from '../components/animations/PageTransition';
import { usePageMeta } from '../hooks/usePageMeta';

export default function CigarDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { daysFilter, setDaysFilter } = useUIStore();
  const { data, isLoading, error, refetch } = usePriceHistory(id, daysFilter);
  const { setMeta } = usePageMeta();

  useEffect(() => {
    if (data) {
      setMeta({
        title: `${data.cigar_name} - 价格追踪`,
        breadcrumbs: [
          { label: '首页', to: '/' },
          { label: '价格追踪', to: '/prices' },
          { label: data.cigar_name },
        ],
      });
    }
  }, [data, setMeta]);

  if (isLoading) return <LoadingState text="加载雪茄详情…" />;
  if (error) return <ErrorState message="数据加载失败，请刷新重试" onRetry={() => refetch()} />;
  if (!data) return <EmptyState title="暂无数据" description="该雪茄暂无价格记录" />;

  const variants = data.variants || [];
  
  // 排序：在售的放前面，下架/售罄的放最后
  const sortedVariants = [...variants].sort((a, b) => {
    const aInStock = a.in_stock !== false && !a.delisted;
    const bInStock = b.in_stock !== false && !b.delisted;
    if (aInStock === bInStock) return 0;
    return aInStock ? -1 : 1;
  });

  return (
    <PageTransition>
      <div>
        <BackButton onClick={() => navigate('/prices')} />
        <DetailHeader data={data} />

        {variants.length === 0 && (
          <EmptyState
            title="暂无价格记录"
            description="等下次爬虫抓取后数据就会出现在这里"
          />
        )}

        {variants.length > 0 && (
          <>
            <DaysFilter days={daysFilter} onChange={setDaysFilter} />
            <VariantGrid variants={sortedVariants} />
            <PriceChart variants={sortedVariants} />
          </>
        )}
      </div>
    </PageTransition>
  );
}
