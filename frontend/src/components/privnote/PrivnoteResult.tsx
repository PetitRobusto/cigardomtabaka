import { useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Copy, Download, LoaderCircle, RefreshCw, X } from 'lucide-react';
import { createPrivnoteQrImage } from '../../lib/privnoteQr';
import { useDialogFocus } from '../../hooks/useDialogFocus';

interface Props {
  url: string;
  token: string;
  onCreateNew: () => void;
  onViewRecords: () => void;
}

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

async function copyLink(url: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(url);
    return true;
  } catch {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const field = document.createElement('textarea');
    field.value = url;
    field.readOnly = true;
    field.style.position = 'fixed';
    field.style.opacity = '0';
    document.body.appendChild(field);
    try {
      field.select();
      return document.execCommand('copy');
    } catch {
      return false;
    } finally {
      field.remove();
      previous?.focus();
    }
  }
}

function ResultContent({ url, onCreateNew, onViewRecords }: Props) {
  const [qr, setQr] = useState<{ status: 'loading' | 'error' | 'ready'; source: string }>({ status: 'loading', source: '' });
  const [attempt, setAttempt] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const [copyState, setCopyState] = useState<'idle' | 'copying' | 'copied' | 'error'>('idle');
  const titleId = useId();

  useEffect(() => {
    let active = true;
    void createPrivnoteQrImage(url).then(
      source => { if (active) setQr({ status: 'ready', source }); },
      () => { if (active) setQr({ status: 'error', source: '' }); },
    );
    return () => { active = false; };
  }, [url, attempt]);

  useEffect(() => {
    if (copyState !== 'copied') return;
    const timer = window.setTimeout(() => setCopyState('idle'), 2000);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  const copy = async () => {
    setCopyState('copying');
    setCopyState(await copyLink(url) ? 'copied' : 'error');
  };

  return (
    <section aria-labelledby={titleId} className="mx-auto max-w-4xl overflow-hidden rounded-lg border border-border bg-white">
      <header className="flex items-center gap-3 border-b border-border px-5 py-4">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-700"><Check className="h-5 w-5" /></span>
        <div>
          <h2 id={titleId} className="font-display text-xl font-semibold text-fg">链接已生成</h2>
          <p className="mt-1 text-sm text-muted">把链接或二维码发给客户即可</p>
        </div>
      </header>
      <div className="grid gap-6 p-5 md:grid-cols-[minmax(0,1fr)_240px]">
        <div className="min-w-0">
          <p className="mb-2 text-sm font-medium text-fg">私密链接</p>
          <code className="block select-all break-all rounded border border-border bg-cream p-3 text-sm leading-6 text-fg">{url}</code>
          <button type="button" onClick={() => void copy()} disabled={copyState === 'copying'} className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded bg-accent px-5 py-2 text-sm font-medium text-white hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold focus-visible:outline-offset-2 disabled:opacity-60 md:w-auto">
            {copyState === 'copied' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copyState === 'copied' ? '已复制' : copyState === 'copying' ? '复制中…' : '复制链接'}
          </button>
          <div aria-live="polite" className="mt-2 min-h-5 text-xs text-accent">
            {copyState === 'error' && '复制失败，请选择上方链接手动复制。'}
            {copyState === 'copied' && '链接已复制'}
          </div>
          <p className="mt-4 border-t border-border pt-4 text-sm leading-6 text-muted">二维码打开同一链接，共用有效期、密码和查看限制。保存或放大二维码不会消耗查看次数。</p>
        </div>
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
      </div>
      <footer className="flex flex-wrap items-center gap-3 border-t border-border px-5 py-4">
        <button type="button" onClick={onCreateNew} className={secondary}>创建新的链接</button>
        <button type="button" onClick={onViewRecords} className={secondary}>查看访问记录</button>
      </footer>
      {zoomed && qr.status === 'ready' && <QrZoom source={qr.source} onClose={() => setZoomed(false)} />}
    </section>
  );
}

// A new URL starts a fresh result, including any in-flight image/copy operation.
export default function PrivnoteResult(props: Props) {
  return <ResultContent key={props.url} {...props} />;
}
