const SOURCE_STYLES: Record<string, string> = {
  coh: 'bg-stone-100 text-stone-500 border-stone-200',
  ihavanas: 'bg-gold-50 text-gold-700 border-gold-200',
  egm: 'bg-cream text-stone-700 border-stone-300',
  lcdh_nyon: 'bg-blue-50 text-blue-700 border-blue-200',
};

export function SourceTag({ slug, shortName }: { slug: string; shortName?: string }) {
  const label = shortName || slug.toUpperCase();
  const style = SOURCE_STYLES[slug] || 'bg-stone-100 text-stone-500 border-stone-200';
  return (
    <span className={`inline-block text-[0.65rem] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${style}`}>
      {label}
    </span>
  );
}
