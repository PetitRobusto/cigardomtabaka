export const AGE_CONFIRMATION_KEY = "cdt-store-age-confirmed";
const AGE_CONFIRMATION_TTL_MS = 30 * 24 * 60 * 60 * 1000;

export function isAgeConfirmationValid(savedValue: string | null, now = Date.now()): boolean {
  if (savedValue === null || savedValue.trim() === "") return false;
  const savedAt = Number(savedValue);
  const age = now - savedAt;
  return Number.isFinite(savedAt) && age >= 0 && age < AGE_CONFIRMATION_TTL_MS;
}
