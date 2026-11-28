import { Component, type ReactNode } from 'react';
import { localeForPath, notFoundCopy } from '../site/notFoundCopy';
import { commerceCopy } from '../../storefront/commerceCopy';
import { homePath } from '../../storefront/browsing';
import { useStartupReady } from '../../hooks/useStartupReady';
import '../site/not-found.css';

export function PageError() {
  useStartupReady();
  const locale = localeForPath(window.location.pathname);
  const copy = commerceCopy[locale];
  return (
    <main className="not-found-page page-error" lang={locale}>
      <div role="alert"><h1 className="not-found-heading">{copy.pageUnavailable}</h1></div>
      <div className="not-found-actions">
        <button className="not-found-primary" type="button" onClick={() => window.location.reload()}>{copy.retry}</button>
        <a className="not-found-home" href={homePath(locale)}>{notFoundCopy[locale].home}</a>
      </div>
    </main>
  );
}

// The prerendered storefront hydrates independently of React Router.
export class StorefrontErrorBoundary extends Component<{ children: ReactNode }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? <PageError /> : this.props.children;
  }
}
