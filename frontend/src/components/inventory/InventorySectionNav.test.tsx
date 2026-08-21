import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import InventorySectionNav from './InventorySectionNav';

function renderAt(path: string) {
  return renderToStaticMarkup(<MemoryRouter initialEntries={[path]}><InventorySectionNav /></MemoryRouter>);
}

describe('InventorySectionNav', () => {
  it('links both inventory workspaces and marks stock active only on its exact route', () => {
    const html = renderAt('/inventory');
    expect(html).toContain('aria-label="库存子导航"');
    expect(html).toMatch(/aria-current="page"[^>]*href="\/inventory"/);
    expect(html).toContain('href="/inventory/purchases"');
  });

  it('marks purchase orders active without also activating stock', () => {
    const html = renderAt('/inventory/purchases');
    expect(html).toMatch(/aria-current="page"[^>]*href="\/inventory\/purchases"/);
    expect(html).not.toMatch(/aria-current="page"[^>]*href="\/inventory"/);
  });
});
