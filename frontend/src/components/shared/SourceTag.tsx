const SOURCE_STYLES: Record<string, string> = {
  coh: 'bg-accent-light text-muted border-border',
  ihavanas: 'bg-accent-light text-accent-hover border-accent',
  egm: 'bg-cream text-fg border-border',
  lcdh_nyon: 'bg-blue-50 text-blue-700 border-blue-200',
};

export function SourceTag({ slug, shortName }: { slug: string; shortName?: string }) {
  const label = shortName || slug.toUpperCase();
  const style = SOURCE_STYLES[slug] || 'bg-accent-light text-muted border-border';
  return (
    <span className={`inline-block text-[0.65rem] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${style}`}>
      {label}
    </span>
  );
}
