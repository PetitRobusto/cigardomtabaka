import { useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, LoaderCircle, RefreshCw, X } from 'lucide-react';
import { createPrivnoteQrImage } from '../../lib/privnoteQr';
import { useDialogFocus } from '../../hooks/useDialogFocus';

const secondary = 'inline-flex min-h-11 items-center justify-center gap-2 rounded border border-border bg-white px-4 py-2 text-sm font-medium text-fg hover:border-gold focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold focus-visible:outline-offset-2';
const filename = 'CigarDomTabaka-二维码.png';

function QrZoom({ source, onClose }: { source: string; onClose: () => void }) {
  const ref = useDialogFocus(onClose, false);
  const titleId = useId();
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-fg/50 p-3 backdrop-blur-sm" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className="max-h-[calc(100dvh-24px)] w-full max-w-md overflow-y-auto rounded-lg bg-white text-fg shadow-xl outline-none">
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
          <h2 id={titleId} className="font-display text-xl font-semibold">链接二维码</h2>
          <button type="button" onClick={onClose} aria-label="关闭二维码" className={`${secondary} min-w-11 px-2`}><X className="h-5 w-5" /></button>
        </div>
        <div className="p-5 text-center">
          <img src={source} alt="放大的链接二维码" className="mx-auto max-h-[60dvh] max-w-full object-contain" />
          <p className="mt-3 text-xs text-muted">手机可长按图片保存</p>
          <a href={source} download={filename} className={`${secondary} mt-4 w-full`}><Download className="h-4 w-4" />保存二维码</a>
        </div>
      </div>
    </div>, document.body,
  );
}

function QrContent({ url }: { url: string }) {
  const [qr, setQr] = useState<{ status: 'loading' | 'error' | 'ready'; source: string }>({ status: 'loading', source: '' });
  const [attempt, setAttempt] = useState(0);
  const [zoomed, setZoomed] = useState(false);

  useEffect(() => {
    let active = true;
    void createPrivnoteQrImage(url).then(
      source => { if (active) setQr({ status: 'ready', source }); },
      () => { if (active) setQr({ status: 'error', source: '' }); },
    );
    return () => { active = false; };
  }, [url, attempt]);

  return <>
    <div className="mx-auto w-full max-w-[240px] text-center">
      <div className="flex min-h-[272px] items-center justify-center overflow-hidden rounded border border-border bg-white">
        {qr.status === 'ready' ? (
          <button type="button" aria-label="放大链接二维码" onClick={() => setZoomed(true)} className="block w-full cursor-zoom-in focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-gold">
            <img src={qr.source} alt="链接二维码" className="block h-auto w-full" />
          </button>
        ) : qr.status === 'error' ? (
          <div className="p-4">
            <p role="alert" className="text-sm leading-6 text-accent">二维码生成失败，链接仍可使用。</p>
            <button type="button" onClick={() => { setQr({ status: 'loading', source: '' }); setAttempt(value => value + 1); }} className={`${secondary} mt-3`}><RefreshCw className="h-4 w-4" />重试二维码</button>
          </div>
        ) : (
          <p role="status" className="flex items-center gap-2 text-sm text-muted"><LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" />二维码生成中…</p>
        )}
      </div>
      <p className="mt-2 text-xs leading-5 text-muted">点击二维码放大 · 手机可长按保存</p>
      {qr.status === 'ready' && <a href={qr.source} download={filename} className={`${secondary} mt-3 w-full`}><Download className="h-4 w-4" />保存二维码</a>}
    </div>
    {zoomed && qr.status === 'ready' && <QrZoom source={qr.source} onClose={() => setZoomed(false)} />}
  </>;
}

// Reset the image and discard pending generation when the link changes.
export default function PrivnoteQr({ url }: { url: string }) {
  return <QrContent key={url} url={url} />;
}
