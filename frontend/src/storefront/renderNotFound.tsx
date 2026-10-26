import { renderToStaticMarkup } from 'react-dom/server';
import { NotFoundPage } from '../components/site/NotFoundPage';
import { notFoundCopy } from '../components/site/notFoundCopy';
import { siteFaviconUrl } from '../components/site/siteAssets';
import styles from '../components/site/not-found.css?raw';
import type { StoreLocale } from './types';

/** Build-time HTML, with inline CSS and native links: the HTTP error works without JS or a database. */
export function renderNotFoundDocument(locale: StoreLocale): string {
  return '<!doctype html>' + renderToStaticMarkup(
    <html lang={locale === 'zh' ? 'zh-CN' : locale === 'ru' ? 'ru-RU' : 'en'}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <meta name="robots" content="noindex, nofollow" />
        <title>{notFoundCopy[locale].title}</title>
        <link rel="icon" type="image/png" sizes="96x96" href={siteFaviconUrl} />
        <style dangerouslySetInnerHTML={{ __html: styles }} />
      </head>
      <body className="not-found-document"><NotFoundPage locale={locale} /></body>
    </html>,
  );
}
