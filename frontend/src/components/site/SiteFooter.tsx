import { ArrowUpRight, MessageCircle, Send } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { siteLogoUrl as brandLogoUrl } from './siteAssets';
import { customerMessages, type CustomerLocale } from '../../features/customer/messages';
import publicDetails from '../../../../storefront/public_details.json';
import './site-footer.css';

type SiteFooterDetails = {
  name?: string; address?: string; phone?: string; wechat?: string; map_url?: string; hours?: string;
};

function yandexEmbedUrl(mapUrl: string, locale: CustomerLocale): string | undefined {
  try {
    const url = new URL(mapUrl);
    const token = /^\/maps\/-\/([\w~]+)$/.exec(url.pathname)?.[1];
    if (url.protocol !== 'https:' || !['yandex.com', 'yandex.ru'].includes(url.hostname) || !token) return;
    const lang = locale === 'ru' ? 'ru_RU' : 'en_RU';
    if (url.pathname === new URL(publicDetails.map_url).pathname) {
      // Coordinates are Yandex's entrance "6" geometry, not the shared viewport center.
      const point = publicDetails.map_point.join(',');
      const parameters = new URLSearchParams({ ll: point, z: '18', pt: `${point},pm2rdm`, lang });
      return `https://yandex.com/map-widget/v1/?${parameters}`;
    }
    // Yandex's official frame endpoint resolves the same shared place, without guessing coordinates.
    return `https://api-maps.yandex.ru/frame/v1/-/${token}?lang=${lang}`;
  } catch { return; }
}

function WechatContact({ account, label }: { account: string; label: string }) {
  const [open, setOpen] = useState(false);
  const [cardLeft, setCardLeft] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const cardId = useId();
  const show = () => {
    const bounds = root.current?.getBoundingClientRect();
    if (bounds) setCardLeft(Math.max(24, Math.min(bounds.left, window.innerWidth - 254)) - bounds.left);
    setOpen(true);
  };
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const closeOnResize = () => setOpen(false);
    document.addEventListener('pointerdown', close);
    window.addEventListener('resize', closeOnResize);
    return () => { document.removeEventListener('pointerdown', close); window.removeEventListener('resize', closeOnResize); };
  }, [open]);
  return <div ref={root} className="site-footer-wechat-contact" onMouseEnter={show} onMouseLeave={() => {
    if (!root.current?.contains(document.activeElement)) setOpen(false);
  }} onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={(event) => {
    if (event.key === 'Escape') { event.stopPropagation(); setOpen(false); }
  }}>
    <button type="button" aria-expanded={open} aria-controls={cardId} aria-describedby={open ? cardId : undefined} onFocus={show} onClick={show}>
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false" className="wechat-icon">
        <path d="M8.5 3C3.8 3 0 6.1 0 10c0 2.2 1.2 4.1 3.2 5.4L2.4 18l3-1.5c1 .3 2 .5 3.1.5h.5a6.8 6.8 0 0 1-.5-2.5c0-4 3.6-7.2 8.1-7.5C15.2 4.6 12.1 3 8.5 3Zm-3 4.3a1.1 1.1 0 1 1 0 2.2 1.1 1.1 0 0 1 0-2.2Zm6 0a1.1 1.1 0 1 1 0 2.2 1.1 1.1 0 0 1 0-2.2Z" fillRule="evenodd" />
        <path d="M17 8c-3.9 0-7 2.7-7 6s3.1 6 7 6c.9 0 1.8-.1 2.6-.4l2.4 1.2-.6-2.1c1.6-1.1 2.6-2.8 2.6-4.7 0-3.3-3.1-6-7-6Zm-2.5 3.5a1 1 0 1 1 0 2 1 1 0 0 1 0-2Zm5 0a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z" fillRule="evenodd" />
      </svg><span>{label}</span>
    </button>
    <div id={cardId} className="site-footer-wechat-card" style={{ left: cardLeft }} role="tooltip" hidden={!open}>
      <span>{label}</span><strong>{account}</strong>
    </div>
  </div>;
}

/** Shared by the public store and management pages. */
export function SiteFooter({ locale = 'zh', customerPage = false, inert = false, onPhoneContact, site }: {
  locale?: CustomerLocale; customerPage?: boolean; inert?: boolean; onPhoneContact?: () => void;
  site?: SiteFooterDetails;
}) {
  const text = customerMessages[locale];
  // Public storefront fields have already passed the backend's verification gate.
  const name = site?.name?.trim() || 'CigarDomTabaka';
  const address = site?.address?.trim() || publicDetails.address[locale];
  const phone = site?.phone?.trim() || publicDetails.phone;
  const wechat = site?.wechat?.trim() || 'cigardomtabaka';
  const mapUrl = site?.map_url?.trim() || publicDetails.map_url;
  const mapEmbed = yandexEmbedUrl(mapUrl, locale);
  const hours = site ? site.hours?.trim() : publicDetails.hours[locale];
  const telephone = phone.replace(/[^\d+]/g, '');
  return (
    <footer id="store-contact" inert={inert} className="site-footer">
      <div className="site-footer-inner">
        <div className={`site-footer-top${mapEmbed ? ' site-footer-top-with-map' : ''}`}>
          <div className="site-footer-info">
            <div className="site-footer-brand">
              <img src={brandLogoUrl} alt={name} width="120" height="120" loading="lazy" decoding="async" />
              <div>
                <div>{name}</div>
                <div>{text.storeTagline}</div>
              </div>
            </div>

            <div className="site-footer-contacts">
              <div className="site-footer-group">
                <h2>{text.storeAddress}</h2>
                <address>{address}</address>
              </div>
              {hours && <div className="site-footer-group">
                <h2>{text.storeHours}</h2>
                <p>{hours}</p>
              </div>}
              <div className="site-footer-group">
                <h2>{text.storePhone}</h2>
                <a className="site-footer-phone" href={`tel:${telephone}`} onClick={onPhoneContact}>{phone}</a>
              </div>
              <div className="site-footer-group site-footer-social-group">
                <h2>{text.storeSocial}</h2>
                <div className="site-footer-social">
                  <a href="https://t.me/+79296384878" target="_blank" rel="noopener noreferrer" aria-label="Telegram: +79296384878">
                    <Send aria-hidden="true" /><span>Telegram</span><ArrowUpRight aria-hidden="true" />
                  </a>
                  <a href={`https://wa.me/${publicDetails.whatsapp.replace(/\D/g, '')}`} target="_blank" rel="noopener noreferrer" aria-label={`WhatsApp: ${publicDetails.whatsapp}`}>
                    <MessageCircle aria-hidden="true" /><span>WhatsApp</span><ArrowUpRight aria-hidden="true" />
                  </a>
                  <WechatContact account={wechat} label={text.storeWechat} />
                </div>
              </div>
            </div>
          </div>

          {mapEmbed && <div className="site-footer-map">
            <iframe src={mapEmbed} title={text.storeMap} width="560" height="330" loading="lazy" allowFullScreen />
            <a className="site-footer-map-open" href={mapUrl} target="_blank" rel="noopener noreferrer">{text.storeMapOpen}<ArrowUpRight aria-hidden="true" /></a>
          </div>}
        </div>

        <div className="site-footer-bottom">
          &copy; {name}. {customerPage ? text.copyright : 'Все права защищены.'}
        </div>
      </div>
    </footer>
  );
}
