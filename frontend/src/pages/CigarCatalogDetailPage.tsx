import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, Cigarette, Ruler, Maximize2, Package, Image as ImageIcon, X } from 'lucide-react';
import { fetchCigarDetail } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';

export default function CigarCatalogDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [lightbox, setLightbox] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['cigar', id],
    queryFn: () => fetchCigarDetail(id!),
    enabled: !!id,
  });

  if (isLoading) return <LoadingState text="加载雪茄详情…" />;
  if (error) return <ErrorState message="数据加载失败" onRetry={() => refetch()} />;
  if (!data) return <EmptyState title="雪茄不存在" />;

  const { cigar, brand, images_by_type, related, children } = data;
  const allImages = Object.values(images_by_type).flat();

  return (
    <div className="animate-fade-in">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-muted mb-6">
        <Link to="/" className="hover:text-accent transition-colors">所有品牌</Link>
        <span>/</span>
        {brand && (
          <>
            <Link to={`/brand/${brand.slug}`} className="hover:text-accent transition-colors">{brand.name}</Link>
            <span>/</span>
          </>
        )}
        <span className="text-fg truncate">{cigar.name || cigar.english_name}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Header */}
          <div>
            <h1 className="font-display text-2xl font-semibold text-fg">{cigar.name || cigar.english_name}</h1>
            {cigar.name && cigar.english_name !== cigar.name && (
              <p className="text-muted text-sm mt-1">{cigar.english_name}</p>
            )}
            <div className="flex flex-wrap items-center gap-2 mt-3">
              {cigar.release_type_cn && (
                <span className="text-xs px-2 py-1 rounded bg-accent-light text-accent border border-accent/20 font-medium">
                  {cigar.release_type_cn}
                </span>
              )}
              {cigar.status === 'Discontinued' && (
                <span className="text-xs px-2 py-1 rounded bg-stone-100 text-stone-500 border border-stone-200">
                  已停产
                </span>
              )}
            </div>
          </div>

          {/* Specs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {cigar.length && (
              <div className="bg-white border border-border rounded-md p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted mb-1">
                  <Ruler className="w-3.5 h-3.5" />
                  长度
                </div>
                <div className="text-lg font-semibold text-fg">{Math.round(cigar.length)}<span className="text-xs font-normal text-muted ml-1">mm</span></div>
              </div>
            )}
            {cigar.ring_gauge && (
              <div className="bg-white border border-border rounded-md p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted mb-1">
                  <Maximize2 className="w-3.5 h-3.5" />
                  环径
                </div>
                <div className="text-lg font-semibold text-fg">{Math.round(cigar.ring_gauge)}</div>
              </div>
            )}
            {cigar.vitola && (
              <div className="bg-white border border-border rounded-md p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted mb-1">
                  <Cigarette className="w-3.5 h-3.5" />
                  型号
                </div>
                <div className="text-sm font-semibold text-fg">{cigar.vitola_cn || cigar.vitola}</div>
              </div>
            )}
            {cigar.origin && (
              <div className="bg-white border border-border rounded-md p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted mb-1">
                  <Package className="w-3.5 h-3.5" />
                  产地
                </div>
                <div className="text-sm font-semibold text-fg">{cigar.origin === 'Cuban' ? '古巴' : cigar.origin}</div>
              </div>
            )}
          </div>

          {/* Packagings */}
          {cigar.packagings.length > 0 && (
            <div className="bg-white border border-border rounded-md p-4">
              <h3 className="text-sm font-semibold text-fg mb-3">包装规格</h3>
              <ul className="space-y-1.5">
                {cigar.packagings.map((pkg: string, idx: number) => (
                  <li key={idx} className="text-sm text-fg flex items-start gap-2">
                    <span className="w-1 h-1 rounded-full bg-accent mt-2 shrink-0" />
                    {pkg}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Children */}
          {children.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-fg mb-3">子款 / 特别版</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {children.map(child => (
                  <Link
                    key={child.id}
                    to={`/cigar/${child.id}`}
                    className="flex items-center gap-3 bg-white border border-border rounded-md p-3 hover:border-accent transition-colors"
                  >
                    <div className="w-12 h-12 rounded bg-accent-light flex items-center justify-center shrink-0 overflow-hidden">
                      {child.thumb_url ? (
                        <img src={child.thumb_url} alt={child.name} className="w-full h-full object-contain p-1" />
                      ) : (
                        <Cigarette className="w-5 h-5 text-border" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-fg truncate">{child.name}</div>
                      {child.release_type_cn && (
                        <div className="text-xs text-accent">{child.release_type_cn}</div>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* Images */}
          {allImages.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-fg mb-3 flex items-center gap-2">
                <ImageIcon className="w-4 h-4" />
                图片 ({allImages.length})
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {allImages.map((img, idx) => (
                  <button
                    key={idx}
                    onClick={() => setLightbox(img.url)}
                    className="aspect-square bg-white border border-border rounded-md overflow-hidden hover:border-accent transition-colors"
                  >
                    <img
                      src={img.thumbnail_url || img.url}
                      alt=""
                      className="w-full h-full object-contain p-2"
                      loading="lazy"
                    />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Brand Card */}
          {brand && (
            <Link
              to={`/brand/${brand.slug}`}
              className="block bg-white border border-border rounded-md p-4 hover:border-accent transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded bg-accent-light flex items-center justify-center overflow-hidden">
                  {brand.logo_url ? (
                    <img src={brand.logo_url} alt={brand.name} className="w-full h-full object-contain p-1" />
                  ) : (
                    <span className="font-display text-lg text-accent">{brand.name[0]}</span>
                  )}
                </div>
                <div>
                  <div className="text-sm font-medium text-fg">{brand.name}</div>
                  <div className="text-xs text-muted">{brand.english_name}</div>
                </div>
              </div>
            </Link>
          )}

          {/* Related */}
          {related.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-fg mb-3">同品牌推荐</h3>
              <div className="space-y-2">
                {related.map(r => (
                  <Link
                    key={r.id}
                    to={`/cigar/${r.id}`}
                    className="flex items-center gap-3 bg-white border border-border rounded-md p-2.5 hover:border-accent transition-colors"
                  >
                    <div className="w-10 h-10 rounded bg-accent-light flex items-center justify-center shrink-0 overflow-hidden">
                      {r.thumb_url ? (
                        <img src={r.thumb_url} alt={r.name} className="w-full h-full object-contain p-1" />
                      ) : (
                        <Cigarette className="w-4 h-4 text-border" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm text-fg truncate">{r.name}</div>
                      <div className="text-xs text-muted">{r.vitola}</div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center p-4"
          onClick={() => setLightbox(null)}
        >
          <button className="absolute top-4 right-4 text-white/70 hover:text-white">
            <X className="w-6 h-6" />
          </button>
          <img
            src={lightbox}
            alt=""
            className="max-w-full max-h-[90vh] object-contain"
            onClick={e => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
