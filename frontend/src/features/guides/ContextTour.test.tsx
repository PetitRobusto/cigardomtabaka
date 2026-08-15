import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import ContextTour from './ContextTour';

describe('ContextTour SSR 契约', () => {
  it('SSR 没有真实 target 时不伪造任何业务提交控件', () => {
    const html = renderToStaticMarkup(<MemoryRouter initialEntries={['/accounting']}><ContextTour stepId="accounting-actions-exchange" onAction={() => undefined} onMissingTarget={() => undefined} /></MemoryRouter>);
    expect(html).not.toMatch(/type="submit"|onClick=.*submit/i);
  });
});
