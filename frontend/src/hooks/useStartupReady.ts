import { useEffect } from 'react';

// Release the startup overlay when either the page or its error fallback mounts.
export function useStartupReady() {
  useEffect(() => {
    document.documentElement.dataset.cdtAppReady = 'true';
    window.dispatchEvent(new Event('cdt:app-ready'));
    const startup = (window as Window & { CDTStartup?: { ready(): void } }).CDTStartup;
    startup?.ready();
  }, []);
}
