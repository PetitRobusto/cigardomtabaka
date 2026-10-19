import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { findPublicPage, localeContacts, localeHome, site, type Locale } from '../../seo/metadata';

export function LanguageLinks() {
  const { pathname } = useLocation();
  const page = findPublicPage(pathname);
  if (!page || Object.keys(page.alternates).length < 2) return null;
  const labels = { 'zh-CN': '中文', ru: 'Русский', en: 'English' };
  return <nav aria-label={site.locales[page.locale].language} className="flex flex-wrap items-center gap-3 text-xs">
    {Object.entries(page.alternates).map(([locale, path]) => <Link key={locale} to={path!} lang={locale} aria-current={locale === page.locale ? 'page' : undefined} className={locale === page.locale ? 'font-semibold text-accent' : 'text-muted hover:text-fg'}>{labels[locale as Locale]}</Link>)}
  </nav>;
}

export function CatalogNotice({ locale = 'zh-CN' }: { locale?: Locale }) {
  return <p className="my-5 max-w-3xl text-sm leading-6 text-muted">{site.locales[locale].notice}</p>;
}

export function OpeningHours({ locale = 'zh-CN' }: { locale?: Locale }) {
  const copy = site.locales[locale];
  return <div className="space-y-1 text-sm leading-6"><p>{copy.hoursWeek}</p><p>{copy.hoursSunday}</p><p className="text-xs text-muted">{copy.localTime}</p></div>;
}

export function StoreIntroduction({ locale = 'zh-CN' }: { locale?: Locale }) {
  const copy = site.locales[locale];
  return <section className="mb-9 border-b border-border pb-8">
    <p className="mb-3 text-xs uppercase tracking-widest text-muted">CigarDomTabaka · Moscow</p>
    <h1 className="font-display text-3xl font-semibold leading-tight text-fg sm:text-4xl">{copy.home}</h1>
    <p className="mt-4 max-w-2xl text-base leading-7">{copy.intro}</p>
    <div className="mt-6 flex flex-wrap items-center gap-5">
      <Link to={localeContacts(locale)} className="inline-flex min-h-11 items-center rounded bg-accent px-5 py-2.5 text-sm font-semibold text-white">{copy.contacts}</Link>
      <OpeningHours locale={locale} />
    </div>
  </section>;
}

export function BrandEditorial({ slug, locale = 'zh-CN' }: { slug: string; locale?: Locale }) {
  const editorial = site.brands[slug as keyof typeof site.brands] as Partial<Record<Locale, string>> | undefined;
  return <section className="my-6 max-w-3xl text-sm leading-7">
    {editorial?.[locale] && <p>{editorial[locale]}</p>}
    <CatalogNotice locale={locale} />
    <Link to={localeContacts(locale)} className="text-accent underline underline-offset-4">{site.locales[locale].contacts}</Link>
  </section>;
}

export function StoreContactDetails({ locale = 'zh-CN' }: { locale?: Locale }) {
  const [copied, setCopied] = useState(false);
  const copy = site.locales[locale];
  async function copyAddress() {
    try { await navigator.clipboard.writeText(site.address); setCopied(true); }
    catch { setCopied(false); }
  }
  return <div className="grid gap-4 sm:grid-cols-2">
    <section className="rounded border border-border bg-white p-5 sm:p-6">
      <h2 className="text-sm font-semibold text-muted">{copy.addressTitle}</h2>
      <p lang="ru" className="mt-3 break-words font-display text-xl">{site.address}</p>
      <p className="mt-3 text-sm leading-6 text-muted">{copy.addressHelp}</p>
      <button type="button" onClick={() => { void copyAddress(); }} className="mt-4 min-h-11 rounded border border-border px-4 text-sm">{copy.copyAddress}</button>
      <span role="status" className="ml-3 text-xs text-muted">{copied ? copy.copied : ''}</span>
      {site.mapUrl && <a href={site.mapUrl} className="mt-3 block text-sm text-accent">Yandex Maps</a>}
    </section>
    <section className="rounded border border-border bg-white p-5 sm:p-6"><h2 className="text-sm font-semibold text-muted">{copy.hoursTitle}</h2><div className="mt-3"><OpeningHours locale={locale} /></div></section>
    <section className="rounded border border-border bg-white p-5 sm:p-6"><h2 className="text-sm font-semibold text-muted">{copy.phoneTitle}</h2><a href={site.phoneHref} className="mt-3 inline-flex min-h-11 items-center break-all text-lg text-accent">{site.phone}</a></section>
    <section className="rounded border border-border bg-white p-5 sm:p-6"><h2 className="text-sm font-semibold text-muted">{copy.wechatTitle}</h2><p className="mt-3 break-all font-mono text-lg">{site.wechat}</p></section>
  </div>;
}

export function ContactPage({ locale = 'zh-CN' }: { locale?: Locale }) {
  const copy = site.locales[locale];
  return <div><h1 className="mb-7 font-display text-3xl font-semibold">{copy.contacts}</h1><StoreContactDetails locale={locale} /><Link to={localeHome(locale)} className="mt-8 inline-flex min-h-11 items-center text-sm text-accent">← {copy.back}</Link></div>;
}
