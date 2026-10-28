import type { ReactElement } from 'react';
import { customerMessages, type CustomerLocale } from '../../features/customer/messages';
import './startup-loader.css';

export interface StartupLoaderProps {
  locale: CustomerLocale;
}

/** Server-renderable overlay markup shared by the Django SPA shell and storefront SSR. */
export function StartupLoader({ locale }: StartupLoaderProps): ReactElement {
  const messages = customerMessages[locale];

  return (
    <section
      id="startup-loader"
      data-locale={locale}
      lang={locale === 'zh' ? 'zh-CN' : locale}
      data-phase="intro"
      data-slow-text={messages.loading}
      data-failed-text={messages.loadError}
      data-retry-text={messages.retry}
      aria-busy="true"
      aria-label={messages.loading}
      hidden
    >
      <div className="cdt-startup__surface" aria-hidden="true" />
      <div className="cdt-startup__composition">
        <img
          className="cdt-startup__logo"
          data-motion-src="/static/frontend/logo-opening-motion-v2.svg"
          data-static-src="/static/frontend/logo-motion-376.webp"
          data-static-srcset="/static/frontend/logo-motion-376.webp 376w, /static/frontend/logo-motion-564.webp 564w, /static/frontend/logo-motion-640.webp 640w"
          data-static-sizes="(max-height: 420px) 132px, (max-width: 520px) 156px, 188px"
          width="640"
          height="525"
          alt=""
          aria-hidden="true"
        />
        <div className="cdt-startup__status" role="status" aria-live="polite" aria-atomic="true">
          <span className="cdt-startup__status-copy">
            <span className="cdt-startup__status-label">{messages.loading}</span>
            <span className="cdt-loading-dots" aria-hidden="true"><i /><i /><i /></span>
          </span>
        </div>
        <div className="cdt-startup__recovery">
          <button className="cdt-startup__retry" type="button" hidden>{messages.retry}</button>
        </div>
      </div>
    </section>
  );
}

export default StartupLoader;
