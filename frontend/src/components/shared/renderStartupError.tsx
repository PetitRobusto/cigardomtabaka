import { createRoot } from 'react-dom/client';
import { PageError } from './PageError';

export function renderStartupError(container: HTMLElement | null) {
  const target = container ?? document.body.appendChild(document.createElement('div'));
  createRoot(target).render(<PageError />);
}
