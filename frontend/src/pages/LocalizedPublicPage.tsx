import { useQuery } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { fetchBrandDetail, fetchBrandList } from '../api';
import { BrandEditorial, CatalogNotice, ContactPage, StoreIntroduction } from '../components/public/StoreContent';
import { ErrorState } from '../components/shared/ErrorState';
import { LoadingState } from '../components/shared/LoadingState';
import { findPublicPage, site } from '../seo/metadata';
import { generateCigarSlugFromParts } from '../utils/slug';

export default function LocalizedPublicPage() {
  const { pathname } = useLocation();
  const page = findPublicPage(pathname)!;
  const { locale } = page;
  const copy = site.locales[locale];
  const home = useQuery({ queryKey: ['brands'], queryFn: fetchBrandList, enabled: page.kind === 'home' });
  const brand = useQuery({ queryKey: ['brand', 'cohiba'], queryFn: () => fetchBrandDetail('cohiba'), enabled: page.kind === 'brand' });
  if (page.kind === 'contacts') return <ContactPage locale={locale} />;
  const query = page.kind === 'home' ? home : brand;
  if (query.isError) return <ErrorState message={locale === 'ru' ? 'Не удалось загрузить каталог' : 'Unable to load the catalogue'} onRetry={() => { void query.refetch(); }} />;
  if (query.isLoading) return <LoadingState text={locale === 'ru' ? 'Загрузка…' : 'Loading…'} />;
  if (page.kind === 'home') {
    const brands = home.data?.sections.flatMap(section => section.brands).filter(item => item.slug in site.brands) || [];
    return <><StoreIntroduction locale={locale} /><h2 className="mb-5 font-display text-2xl font-semibold">{copy.brandHeading}</h2><div className="grid gap-4 sm:grid-cols-2">
      {brands.map(item => <Link key={item.slug} to={item.slug === 'cohiba' ? `/${locale}/brand/cohiba` : `/brand/${item.slug}`} className="rounded border border-border bg-white p-5">
        <h3 className="font-display text-xl">{item.english_name}</h3><p className="mt-2 text-xs text-muted">{item.slug === 'cohiba' ? copy.details : locale === 'ru' ? 'Каталог на китайском языке' : 'Chinese-language catalogue'}</p>
      </Link>)}
    </div><CatalogNotice locale={locale} /></>;
  }
  const models = brand.data?.sections.flatMap(section => section.cigars) || [];
  return <><h1 className="font-display text-3xl font-semibold">{locale === 'ru' ? 'Кубинские сигары Cohiba' : 'Cuban Cohiba cigars'}</h1><BrandEditorial slug="cohiba" locale={locale} />
    <h2 className="mb-4 font-display text-xl font-semibold">{copy.models}</h2>
    <p className="mb-4 text-sm text-muted">{locale === 'ru' ? 'Подробные карточки моделей — на китайском языке.' : 'Detailed model pages are available in Chinese.'}</p>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{models.map(cigar => <Link key={cigar.id} to={`/cigar/${cigar.id}/${generateCigarSlugFromParts('Cohiba', cigar.english_name, cigar.release_type)}`} className="rounded border border-border bg-white p-4">
      <h3 className="font-display text-lg">Cohiba {cigar.english_name}</h3><p className="mt-2 text-xs text-muted">{cigar.length ? `${cigar.length} mm` : '—'} · {locale === 'ru' ? 'Кольцо' : 'Ring gauge'} {cigar.ring_gauge || '—'}</p>
    </Link>)}</div>
  </>;
}
