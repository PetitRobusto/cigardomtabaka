import { useEffect, useEffectEvent, useRef, type InputHTMLAttributes } from 'react';
import flatpickr from 'flatpickr';
import { Mandarin } from 'flatpickr/dist/l10n/zh';
import type { Instance } from 'flatpickr/dist/types/instance';
import 'flatpickr/dist/flatpickr.min.css';

type DateFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'value' | 'onChange'> & {
  value: string;
  onChange: (event: { target: HTMLInputElement }) => void;
};

export default function DateField({ value, onChange, ...props }: DateFieldProps) {
  const input = useRef<HTMLInputElement>(null);
  const calendar = useRef<Instance | null>(null);
  const notify = useEffectEvent((target: HTMLInputElement) => onChange({ target }));

  useEffect(() => {
    const field = input.current;
    if (!field || field.disabled || field.readOnly) return;
    const dateCheck = document.createElement('input');
    dateCheck.type = 'date';
    dateCheck.min = field.min;
    dateCheck.max = field.max;
    const dialog = field.closest<HTMLElement>('dialog, [aria-modal="true"]');
    const picker = flatpickr(field, {
      minDate: field.min || undefined,
      maxDate: field.max || undefined,
      ...(dialog ? {
        appendTo: dialog,
        position: (instance: Instance) => {
          const popup = instance.calendarContainer;
          const bounds = field.getBoundingClientRect();
          const top = bounds.bottom + popup.offsetHeight <= window.innerHeight ? bounds.bottom : bounds.top - popup.offsetHeight;
          popup.style.position = 'fixed';
          popup.style.top = Math.max(0, top) + 'px';
          popup.style.left = Math.max(0, Math.min(bounds.left, window.innerWidth - popup.offsetWidth)) + 'px';
        },
      } : {}),
      locale: Mandarin,
      parseDate: (text: string) => {
        dateCheck.value = text;
        return new Date(dateCheck.value ? dateCheck.value + 'T00:00:00' : NaN);
      },
      dateFormat: 'Y-m-d',
      ariaDateFormat: 'Y-m-d',
      disableMobile: true,
      allowInput: true,
      onReady: (_, __, instance) => instance.calendarContainer.setAttribute('aria-hidden', 'true'),
      onOpen: (_, __, instance) => instance.calendarContainer.removeAttribute('aria-hidden'),
      onClose: (_, __, instance) => instance.calendarContainer.setAttribute('aria-hidden', 'true'),
    });
    calendar.current = picker;
    if (!field.required) {
      const clear = document.createElement('button');
      clear.type = 'button';
      clear.className = 'w-full border-t border-border py-2 text-sm text-muted';
      clear.textContent = '清除日期';
      clear.onclick = () => { picker.clear(); field.focus({ preventScroll: true }); picker.close(); };
      picker.calendarContainer.append(clear);
    }
    const changed = () => {
      dateCheck.value = field.value;
      if (!dateCheck.value || !dateCheck.validity.valid) field.value = '';
      notify(field);
    };
    const closeCalendar = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && picker.isOpen) {
        event.preventDefault();
        event.stopPropagation();
        field.focus({ preventScroll: true });
        picker.close();
      }
    };
    field.addEventListener('change', changed);
    field.addEventListener('keydown', closeCalendar, true);
    picker.calendarContainer.addEventListener('keydown', closeCalendar, true);
    return () => {
      field.removeEventListener('change', changed);
      field.removeEventListener('keydown', closeCalendar, true);
      picker.calendarContainer.removeEventListener('keydown', closeCalendar, true);
      picker.destroy();
      calendar.current = null;
    };
  }, [props.disabled, props.readOnly, props.required, props.min, props.max]);

  useEffect(() => {
    const field = input.current;
    if (!field) return;
    calendar.current?.setDate(value, false);
    field.value = value;
    const outsideRange = value && ((field.min && value < field.min) || (field.max && value > field.max));
    field.setCustomValidity(outsideRange ? '请选择允许范围内的日期' : '');
  }, [value, props.disabled, props.readOnly, props.required, props.min, props.max]);

  return <input ref={input} {...props} type="text" inputMode="none" defaultValue={value} placeholder="年-月-日" autoComplete="off" />;
}
