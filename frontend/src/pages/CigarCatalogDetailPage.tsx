import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Cigarette, Image as ImageIcon, X } from 'lucide-react';
import { fetchCigarDetail } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import { usePageMeta } from '../hooks/usePageMeta';
import { generateCigarSlugFromParts } from '../utils/slug';

export default function CigarCatalogDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [lightbox, setLightbox] = useState<string | null>(null);
  const { setMeta } = usePageMeta();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['cigar', id],
    queryFn: () => fetchCigarDetail(id!),
    enabled: !!id,
  });

  useEffect(() => {
    if (data?.cigar) {
      setMeta({
        title: `${data.cigar.name || data.cigar.english_name} · ${data.brand?.name || data.cigar.brand}`,
        breadcrumbs: [
          { label: '首页', to: '/' },
          { label: data.brand?.name || data.cigar.brand, to: data.brand ? `/brand/${data.brand.slug}` : undefined },
          { label: data.cigar.name || data.cigar.english_name },
        ],
      });
    }
  }, [data, setMeta]);

  if (isLoading) return <LoadingState text="加载雪茄详情…" />;
  if (error) return <ErrorState message="数据加载失败" onRetry={() => refetch()} />;
  if (!data) return <EmptyState title="雪茄不存在" />;

  const { cigar, brand, images_by_type, related, children } = data;
  const allImages = Object.values(images_by_type).flat();

  // Find hero image: primary non-band image first, then first non-band, then first
  const heroImage = allImages.find(img => img.is_primary && img.image_type !== 'band')
    || allImages.find(img => img.image_type !== 'band')
    || allImages[0]
    || null;

  // Gallery images excluding hero
  const galleryImages = heroImage
    ? allImages.filter(img => img.url !== heroImage.url)
    : allImages;

  const isCuban = cigar.origin === 'Cuban';

  // Build quick specs items
  const quickSpecs: { label: string; value: React.ReactNode; accent?: boolean }[] = [];
  if (brand) {
    quickSpecs.push({
      label: '品牌',
      value: (
        <Link to={`/brand/${brand.slug}`} className="text-accent hover:underline">
          {brand.name}
        </Link>
      ),
    });
  }
  if (cigar.origin) {
    quickSpecs.push({ label: '产地', value: isCuban ? '古巴' : cigar.origin });
  }
  if (cigar.length) {
    quickSpecs.push({ label: '长度', value: `${Math.round(cigar.length)} mm` });
  }
  if (cigar.ring_gauge) {
    quickSpecs.push({ label: '环径', value: `${Math.round(cigar.ring_gauge)}` });
  }

  return (
    <div className="animate-fade-in">
      {/* Title Section */}
      <section className="py-6 sm:py-8">
        <h1 className="font-display text-[28px] sm:text-4xl font-semibold tracking-tight text-fg mb-1.5">
          {cigar.name || cigar.english_name}
        </h1>
        {cigar.name && cigar.english_name !== cigar.name && (
          <p className="font-display italic text-lg text-muted mb-4">
            {cigar.english_name}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          {isCuban && (
            <span className="text-xs px-2.5 py-1 rounded border border-accent text-accent font-medium">
              古巴
            </span>
          )}
          {cigar.release_type_cn && (
            <span className="text-xs px-2.5 py-1 rounded border border-border text-muted">
              {cigar.release_type_cn}
            </span>
          )}
          {cigar.status === 'Discontinued' && (
            <span className="text-xs px-2.5 py-1 rounded border border-stone-200 text-stone-500">
              已停产
            </span>
          )}
        </div>
      </section>

      {/* Hero Image */}
      {heroImage && (
        <section className="mb-8">
          <button
            onClick={() => setLightbox(heroImage.url)}
            className="block w-full bg-white border border-border rounded-md overflow-hidden hover:border-accent transition-colors"
          >
            <div className="flex items-center justify-center bg-[#FAF8F5] min-h-[200px] sm:min-h-[280px] max-h-[360px] p-8 sm:p-10">
              <img
                src={heroImage.url}
                alt={cigar.name || cigar.english_name}
                className="max-w-full max-h-[180px] sm:max-h-[220px] object-contain"
                loading="eager"
              />
            </div>
          </button>
        </section>
      )}

      {/* Quick Specs */}
      {quickSpecs.length > 0 && (
        <section className="flex items-center justify-center gap-0 bg-white border border-border rounded-md px-4 sm:px-8 py-5 sm:py-6 mb-8 overflow-x-auto">
          {quickSpecs.map((spec, idx) => (
            <div key={spec.label} className="flex items-center">
              <div className="text-center px-4 sm:px-8 shrink-0">
                <div className="text-[11px] text-muted uppercase tracking-widest mb-1.5">
                  {spec.label}
                </div>
                <div className={`font-display text-lg font-semibold ${spec.accent ? 'text-accent' : 'text-fg'}`}>
                  {spec.value}
                </div>
              </div>
              {idx < quickSpecs.length - 1 && (
                <div className="w-px h-8 bg-border shrink-0" />
              )}
            </div>
          ))}
        </section>
      )}

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-8 items-start">
        {/* Main Column */}
        <div className="min-w-0 space-y-6">

          {/* Spec Detail Card */}
          <div className="bg-white border border-border rounded-md p-5 sm:p-6">
            <div className="text-[13px] text-muted uppercase tracking-wider pb-3 mb-5 border-b border-border">
              规格详情
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-5">
              {cigar.length && (
                <div>
                  <div className="text-[11px] text-muted uppercase tracking-wider mb-1.5">长度</div>
                  <div className="font-display text-xl font-semibold text-fg">{Math.round(cigar.length)} <span className="text-xs font-normal text-muted">mm</span></div>
                </div>
              )}
              {cigar.ring_gauge && (
                <div>
                  <div className="text-[11px] text-muted uppercase tracking-wider mb-1.5">环径</div>
                  <div className="font-display text-xl font-semibold text-fg">{Math.round(cigar.ring_gauge)}</div>
                </div>
              )}
              {(cigar.common_name || cigar.common_name_cn) && (
                <div>
                  <div className="text-[11px] text-muted uppercase tracking-wider mb-1.5">常见名称</div>
                  <div className="font-display text-base font-semibold text-fg">{cigar.common_name_cn || cigar.common_name}</div>
                  {cigar.common_name_cn && cigar.common_name && cigar.common_name_cn !== cigar.common_name && (
                    <div className="text-xs text-muted mt-0.5 font-display italic">{cigar.common_name}</div>
                  )}
                </div>
              )}
              {(cigar.vitola || cigar.vitola_cn) && (
                <div>
                  <div className="text-[11px] text-muted uppercase tracking-wider mb-1.5">工厂型号</div>
                  <div className="font-display text-base font-semibold text-fg">{cigar.vitola_cn || cigar.vitola}</div>
                  {cigar.vitola_cn && cigar.vitola && cigar.vitola_cn !== cigar.vitola && (
                    <div className="text-xs text-muted mt-0.5 font-display italic">{cigar.vitola}</div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Package Section */}
          {cigar.packagings.length > 0 && (
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-4 text-[13px] text-muted uppercase tracking-wider">
                包装规格
              </div>
              <div className="bg-white border border-border rounded-md p-5 sm:p-6">
                <ul className="space-y-0">
                  {cigar.packagings.map((pkg: string, idx: number) => (
                    <li
                      key={idx}
                      className="text-sm text-fg flex items-center gap-2 py-2.5 border-b border-border last:border-b-0"
                    >
                      <span className="w-1 h-1 rounded-full bg-accent shrink-0" />
                      {pkg}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Children */}
          {children.length > 0 && (
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-4 text-[13px] text-muted uppercase tracking-wider">
                子款 / 特别版
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {children.map(child => (
                  <Link
                    key={child.id}
                    to={`/cigar/${child.id}/${generateCigarSlugFromParts(cigar.brand, child.english_name, child.release_type)}`}
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

          {/* Gallery Images */}
          {galleryImages.length > 0 && (
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-4 text-[13px] text-muted uppercase tracking-wider">
                <ImageIcon className="w-4 h-4" />
                图片 ({galleryImages.length})
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {galleryImages.map((img, idx) => (
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
        <div className="min-w-0 lg:sticky lg:top-[72px] space-y-5">
          {/* Brand Card */}
          {brand && (
            <div className="bg-white border border-border rounded-md overflow-hidden">
              <div className="px-5 py-4 border-b border-border text-[13px] text-muted uppercase tracking-wider">
                关于品牌
              </div>
              <div className="p-5">
                <Link
                  to={`/brand/${brand.slug}`}
                  className="flex items-center gap-3 mb-4 group"
                >
                  <div className="w-11 h-11 rounded bg-accent-light flex items-center justify-center overflow-hidden shrink-0">
                    {brand.logo_url ? (
                      <img src={brand.logo_url} alt={brand.name} className="w-full h-full object-contain p-1" />
                    ) : (
                      <span className="font-display text-lg text-accent">{brand.name[0]}</span>
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="font-display text-base font-semibold text-fg group-hover:text-accent transition-colors truncate">
                      {brand.name}
                    </div>
                    <div className="font-display italic text-xs text-muted truncate">
                      {brand.english_name}
                    </div>
                  </div>
                </Link>
                <Link
                  to={`/brand/${brand.slug}`}
                  className="text-[13px] text-accent font-medium hover:underline"
                >
                  查看全部 {brand.cigar_count} 款
                </Link>
              </div>
            </div>
          )}

          {/* Related Cigars */}
          {related.length > 0 && (
            <div className="bg-white border border-border rounded-md overflow-hidden">
              <div className="px-5 py-4 border-b border-border text-[13px] text-muted uppercase tracking-wider">
                同品牌更多雪茄
              </div>
              <div className="px-5">
                {related.map((r, idx) => (
                  <Link
                    key={r.id}
                    to={`/cigar/${r.id}/${generateCigarSlugFromParts(cigar.brand, r.english_name)}`}
                    className={`flex items-center gap-3 py-3 transition-colors hover:bg-accent-light -mx-5 px-5 ${
                      idx < related.length - 1 ? 'border-b border-border' : ''
                    }`}
                  >
                    <div className="w-10 h-10 rounded bg-accent-light flex items-center justify-center shrink-0 overflow-hidden">
                      {r.thumb_url ? (
                        <img src={r.thumb_url} alt={r.name} className="w-full h-full object-contain p-1" />
                      ) : (
                        <Cigarette className="w-4 h-4 text-border" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] font-semibold text-fg truncate">{r.name}</div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="font-display italic text-[11px] text-muted">{r.vitola}</span>
                        {r.release_type_cn && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent text-white shrink-0">
                            {r.release_type_cn}
                          </span>
                        )}
                      </div>
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
