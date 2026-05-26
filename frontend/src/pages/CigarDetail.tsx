import { useParams, useNavigate } from 'react-router-dom';
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

export default function CigarDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { daysFilter, setDaysFilter } = useUIStore();
  const { data, isLoading, error, refetch } = usePriceHistory(id, daysFilter);

  if (isLoading) return <LoadingState text="加载雪茄详情…" />;
  if (error) return <ErrorState message="数据加载失败，请刷新重试" onRetry={() => refetch()} />;
  if (!data) return <EmptyState title="暂无数据" description="该雪茄暂无价格记录" />;

  const variants = data.variants || [];

  return (
    <PageTransition>
      <div>
        <BackButton onClick={() => navigate('/')} />
        <DetailHeader data={data} />

        {variants.length === 0 && (
          <EmptyState
            title="暂无价格记录"
            description="等下次爬虫抓取后数据就会出现在这里"
          />
        )}

        {variants.length > 0 && (
          <>
            <VariantGrid variants={variants} />
            <DaysFilter days={daysFilter} onChange={setDaysFilter} />
            <PriceChart variants={variants} />
          </>
        )}
      </div>
    </PageTransition>
  );
}
