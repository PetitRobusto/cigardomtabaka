import { useEffect, useId, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import PrivnoteQr from './PrivnoteQr';

interface Props {
  url: string;
  token: string;
  onCreateNew: () => void;
  onViewRecords: () => void;
}

const secondary = 'inline-flex min-h-11 items-center justify-center gap-2 rounded border border-border bg-white px-4 py-2 text-sm font-medium text-fg hover:border-gold focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold focus-visible:outline-offset-2';

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
  const [copyState, setCopyState] = useState<'idle' | 'copying' | 'copied' | 'error'>('idle');
  const titleId = useId();

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
        <PrivnoteQr url={url} />
      </div>
      <footer className="flex flex-wrap items-center gap-3 border-t border-border px-5 py-4">
        <button type="button" onClick={onCreateNew} className={secondary}>创建新的链接</button>
        <button type="button" onClick={onViewRecords} className={secondary}>查看访问记录</button>
      </footer>
    </section>
  );
}

// A new URL starts a fresh result, including any in-flight image/copy operation.
export default function PrivnoteResult(props: Props) {
  return <ResultContent key={props.url} {...props} />;
}
