import { useEffect, useRef, type RefObject } from 'react';
import { useCustomerPreferences } from './preferences';
import { useCustomerExperience } from './useCustomerExperience';

export default function CustomerAgeGate({ scope }: { scope: RefObject<HTMLDivElement | null> }) {
  const { text } = useCustomerExperience();
  const { denied, confirmAge, denyAge, reconsiderAge } = useCustomerPreferences();
  const primary = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    primary.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if (event.key === 'Escape') { event.preventDefault(); return; }
      if (event.key !== 'Tab') return;
      // Only the gate, language control and staff login escape are interactive.
      const controls = Array.from(scope.current?.querySelectorAll<HTMLElement>('[data-customer-language] button, [data-age-action], [data-customer-login]') ?? []);
      const index = controls.indexOf(document.activeElement as HTMLElement);
      if (event.shiftKey && index <= 0) { event.preventDefault(); controls[controls.length - 1]?.focus(); }
      else if (!event.shiftKey && (index === controls.length - 1 || index < 0)) { event.preventDefault(); controls[0]?.focus(); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener('keydown', onKeyDown);
      if (previous?.isConnected) previous.focus();
    };
  }, [denied, scope]);

  return <div className="fixed inset-x-0 bottom-0 top-16 z-40 flex items-end justify-center bg-cream/95 sm:items-center sm:p-5">
    <section role="dialog" aria-labelledby="customer-age-title" aria-describedby="customer-age-description"
      className="max-h-full w-full overflow-y-auto rounded-t-xl border border-border bg-white px-6 py-7 pb-[max(1.75rem,env(safe-area-inset-bottom))] shadow-lg sm:max-w-[430px] sm:rounded">
      <p className="text-[10px] font-semibold uppercase tracking-[.14em] text-gold">{text.ageKicker}</p>
      <h1 id="customer-age-title" className="mt-2 font-display text-[22px] font-semibold leading-snug text-fg">{denied ? text.deniedTitle : text.ageTitle}</h1>
      <p id="customer-age-description" className="mt-3 text-sm leading-relaxed text-muted">{denied ? text.deniedBody : text.ageBody}</p>
      <div className="mt-5 grid gap-2.5">
        {denied ? <button ref={primary} type="button" data-age-action onClick={reconsiderAge} className="min-h-11 rounded border border-border bg-white px-4 py-2.5 text-sm font-semibold text-fg hover:border-gold">{text.ageBack}</button> : <>
          <button ref={primary} type="button" data-age-action onClick={confirmAge} className="min-h-11 rounded border border-accent bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-hover">{text.ageYes}</button>
          <button type="button" data-age-action onClick={denyAge} className="min-h-11 rounded border border-border bg-white px-4 py-2.5 text-sm font-semibold text-fg hover:border-gold">{text.ageNo}</button>
        </>}
      </div>
      <p className="mt-3 text-xs leading-relaxed text-muted">{text.ageNote}</p>
    </section>
  </div>;
}
