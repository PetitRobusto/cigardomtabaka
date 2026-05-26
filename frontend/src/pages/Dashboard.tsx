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
import type { CigarListItem, BrandInfo } from '../types';

function extractBrands(cigars: CigarListItem[]): BrandInfo[] {
  const seen = new Set<string>();
  const result: BrandInfo[] = [];
  cigars.forEach((c) => {
    const name = c.cigar_brand_cn || c.cigar_brand;
    if (seen.has(name)) return;
    seen.add(name);
    result.push({
      name,
      nameEn: c.cigar_brand,
      logoUrl: '',
    });
  });
  const BRANDS_ORDER = [
    '高希霸', '蒙特', '罗密欧与朱丽叶', '帕特加斯',
    '好友', '乌普曼',
  ];
  result.sort((a, b) => {
    const ai = BRANDS_ORDER.indexOf(a.name);
    const bi = BRANDS_ORDER.indexOf(b.name);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.name.localeCompare(b.name, 'zh');
  });
  return result;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { activeBrand, setActiveBrand } = useUIStore();
  const { data: cigars = [], isLoading, error, refetch } = useLatestPrices();

  const brands = useMemo(() => extractBrands(cigars), [cigars]);
  const filtered = useMemo(
    () => cigars.filter((g) => !activeBrand || (g.cigar_brand_cn || g.cigar_brand) === activeBrand),
    [cigars, activeBrand]
  );

  if (isLoading) return <LoadingState text="加载价格数据…" />;
  if (error) return <ErrorState message="数据加载失败，请刷新重试" onRetry={() => refetch()} />;
  if (filtered.length === 0) return <EmptyState title="暂无价格数据" description="等待价格数据抓取完成后自动显示" />;

  return (
    <div>
      <StatsBar
        snapshotCount={cigars.reduce((sum, c) => sum + c.sources.length, 0)}
        cigarCount={cigars.length}
        brandCount={brands.length}
        sourceCount={[...new Set(cigars.flatMap(c => c.sources.map(s => s.source_slug)))].length}
      />
      <BrandTabs brands={brands} activeBrand={activeBrand} onSelect={setActiveBrand} />
      <PriceCardGrid cigars={filtered} onCardClick={(id) => navigate(`/cigar/${id}`)} />
    </div>
  );
}
