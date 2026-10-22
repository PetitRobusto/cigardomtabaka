import { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown, Globe } from 'lucide-react';
import { languageNames, languageOptions } from './messages';
import { useCustomerPreferences } from './preferences';
import { useCustomerExperience } from './useCustomerExperience';

export default function CustomerLanguageMenu() {
  const { locale, text } = useCustomerExperience();
  const selectLocale = useCustomerPreferences((state) => state.selectLocale);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', outside);
    return () => document.removeEventListener('pointerdown', outside);
  }, [open]);

  const close = () => { setOpen(false); trigger.current?.focus(); };

  return <div ref={root} className="relative shrink-0" data-customer-language onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={(event) => {
    if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); close(); return; }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    if (!open) { setOpen(true); return; }
    const items = Array.from(root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]') ?? []);
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length;
    items[next]?.focus();
  }}>
    <button ref={trigger} type="button" aria-label={text.language} aria-haspopup="menu" aria-controls={open ? menuId : undefined} aria-expanded={open}
      onClick={() => setOpen(!open)}
      className="inline-flex min-h-11 items-center gap-1.5 rounded border border-border bg-white px-2.5 text-xs font-medium text-fg hover:border-gold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold">
      <Globe className="h-3.5 w-3.5 text-muted" aria-hidden="true" /><span lang={locale === 'zh' ? 'zh-CN' : locale}>{languageNames[locale]}</span><ChevronDown className="h-3 w-3" aria-hidden="true" />
    </button>
    {open && <div id={menuId} role="menu" aria-label={text.language} className="absolute right-0 top-full z-[70] mt-1.5 w-48 max-w-[calc(100vw-2rem)] rounded border border-border bg-white p-1 shadow-lg">
      {languageOptions.map((option) => <button key={option} type="button" role="menuitemradio" aria-checked={locale === option}
        onClick={() => { selectLocale(option); close(); }}
        className={`flex min-h-11 w-full items-center justify-between gap-4 rounded px-3 py-2 text-left text-sm hover:bg-accent-light focus:bg-accent-light focus:outline-none ${locale === option ? 'font-semibold text-accent' : 'text-fg'}`}>
        <span lang={option === 'zh' ? 'zh-CN' : option}>{languageNames[option]}</span>{locale === option && <Check className="h-4 w-4" aria-hidden="true" />}
      </button>)}
    </div>}
  </div>;
}
