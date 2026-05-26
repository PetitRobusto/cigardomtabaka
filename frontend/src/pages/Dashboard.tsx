import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLatestPrices } from '../hooks/useLatestPrices';
import { useUIStore } from '../store/uiStore';
import { StatsBar } from '../components/dashboard/StatsBar';
import { BrandTabs } from '../components/dashboard/BrandTabs';
import { PriceCardGrid } from '../components/dashboard/PriceCardGrid';
import { LoadingState } from '../components/shared/LoadingState';
import { EmptyState } from '../components/shared/EmptyState';
import { ErrorState } from '../components/shared/ErrorState';
import { groupSnapshots, extractBrands, extractSourceSlugs } from '../utils/priceData';

export default function Dashboard() {
  const navigate = useNavigate();
  const { activeBrand, setActiveBrand } = useUIStore();
  const { data: snapshots = [], isLoading, error, refetch } = useLatestPrices();

  const grouped = useMemo(() => groupSnapshots(snapshots), [snapshots]);
  const brands = useMemo(() => extractBrands(grouped), [grouped]);
  const filtered = useMemo(
    () => grouped.filter((g) => !activeBrand || g.brand === activeBrand),
    [grouped, activeBrand]
  );
  const sourceSlugs = useMemo(() => extractSourceSlugs(snapshots), [snapshots]);

  if (isLoading) return <LoadingState text="加载价格数据…" />;
  if (error) return <ErrorState message="数据加载失败，请刷新重试" onRetry={() => refetch()} />;
  if (filtered.length === 0) return <EmptyState title="暂无价格数据" description="等待价格数据抓取完成后自动显示" />;

  return (
    <div>
      <StatsBar
        snapshotCount={snapshots.length}
        cigarCount={new Set(snapshots.map((s) => s.cigar)).size}
        brandCount={brands.length}
        sourceCount={sourceSlugs.length}
      />
      <BrandTabs brands={brands} activeBrand={activeBrand} onSelect={setActiveBrand} />
      <PriceCardGrid cigars={filtered} onCardClick={(id) => navigate(`/cigar/${id}`)} />
    </div>
  );
}
