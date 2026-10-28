import { useSyncExternalStore } from 'react';

function subscribe(onChange: () => void) {
  window.addEventListener('cdt:startup-started', onChange);
  window.addEventListener('cdt:startup-finished', onChange);
  return () => {
    window.removeEventListener('cdt:startup-started', onChange);
    window.removeEventListener('cdt:startup-finished', onChange);
  };
}

/** The standalone loader owns this state, including its final docking frame. */
export function isStartupPending() {
  return document.documentElement.dataset.cdtStarting === 'true';
}

export function useStartupPending() {
  return useSyncExternalStore(subscribe, isStartupPending, () => false);
}
