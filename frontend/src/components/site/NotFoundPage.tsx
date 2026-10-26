import { ArrowRight, ArrowUpRight, MapPin } from 'lucide-react';
import type { StoreLocale } from '../../storefront/types';
import { catalogPath, homePath } from '../../storefront/browsing';
import { siteDockLogoUrl } from './siteAssets';
import { notFoundCopy } from './notFoundCopy';
import publicDetails from '../../../../storefront/public_details.json';
import './not-found.css';

/** The same content is built into HTTP 404 documents and shown after SPA navigation. */
export function NotFoundPage({ locale, embedded = false }: { locale: StoreLocale; embedded?: boolean }) {
  const copy = notFoundCopy[locale];
  const home = homePath(locale);
  const content = <>
    <div className="not-found-code" aria-hidden="true">404<span /></div>
    <div className="not-found-content">
      <h1 id="not-found-heading" className="not-found-heading">{copy.heading}</h1>
      <p className="not-found-message">{copy.message}</p>
      <nav className="not-found-actions" aria-label={copy.navigation}>
        <a className="not-found-primary" href={catalogPath(locale)}>{copy.catalog}<ArrowRight aria-hidden="true" /></a>
        <a className="not-found-home" href={home}>{copy.home}</a>
      </nav>
      <a className="not-found-contact" href={`${home}#store-contact`}>{copy.contact}<ArrowUpRight aria-hidden="true" /></a>
    </div>
  </>;

  if (embedded) return <section className="not-found-page not-found-page--embedded" aria-labelledby="not-found-heading">
    <div className="not-found-main">{content}</div>
  </section>;

  return <div className="not-found-page">
    <header className="not-found-header">
      <a className="not-found-brand" href={home} aria-label="CigarDomTabaka">
        <img src={siteDockLogoUrl} alt="" width="44" height="44" />
        <span>CigarDomTabaka<small>{copy.city}</small></span>
      </a>
      <a className="not-found-header-link" href={catalogPath(locale)}>{copy.catalog}<ArrowUpRight aria-hidden="true" /></a>
    </header>
    <main className="store-main not-found-main" aria-labelledby="not-found-heading">{content}</main>
    <footer className="not-found-footer">
      <a href={publicDetails.map_url} target="_blank" rel="noopener noreferrer"><MapPin aria-hidden="true" /><span>{publicDetails.address[locale]}</span></a>
      <a className="not-found-phone" href={`tel:${publicDetails.phone.replace(/[^\d+]/g, '')}`}>{publicDetails.phone}</a>
    </footer>
  </div>;
}
