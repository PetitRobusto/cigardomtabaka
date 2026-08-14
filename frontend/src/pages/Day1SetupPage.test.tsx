import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { PageMetaProvider } from '../contexts/PageMetaContext';
import { emptyDay1Draft } from '../features/day1/day1State';
import { Day1ReadonlySummary } from './Day1SetupPage';

describe('Day1 page rendering boundary', () => {
  it('renders completed state without any write controls', () => {
    const html = renderToStaticMarkup(
      <PageMetaProvider>
        <MemoryRouter>
          <Day1ReadonlySummary server={{
            status: 'completed',
            version: 3,
            business_date: '2026-08-14',
            draft: null,
            completion_summary: null,
          }} />
        </MemoryRouter>
      </PageMetaProvider>,
    );
    expect(html).toContain('初始化已完成');
    expect(html).not.toContain('保存草稿');
    expect(html).not.toContain('准备生效');
    expect(html).not.toContain('确认并一次性生效');
  });

  it('keeps the local draft as the workflow input when saving fails', async () => {
    const draft = emptyDay1Draft('2026-08-14');
    const save = async () => { throw new Error('版本冲突'); };
    await expect(import('../features/day1/day1Workflow').then(({ saveDay1DraftAtBase }) => saveDay1DraftAtBase({ draft, baseVersion: 2, save }))).rejects.toThrow('版本冲突');
    expect(draft.business_date).toBe('2026-08-14');
    expect(draft.accounts).toHaveLength(4);
  });
});
