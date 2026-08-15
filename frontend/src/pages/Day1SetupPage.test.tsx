import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { PageMetaProvider } from '../contexts/PageMetaContext';
import { emptyDay1Draft } from '../features/day1/day1State';
import { Day1BackgroundButton, Day1ReadonlySummary } from './Day1SetupPage';

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
    // The completed summary is the focus target when confirmation removes its trigger.
    expect(html).toContain('tabindex="-1"');
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

  it('freezes every production background control while confirmation is open', () => {
    const noop = vi.fn();
    const ids = ['refresh', 'discard', 'step-desktop-1', 'step-desktop-2', 'step-desktop-3', 'step-desktop-4', 'step-mobile-1', 'step-mobile-2', 'step-mobile-3', 'step-mobile-4', 'previous', 'save', 'next'];
    const html = renderToStaticMarkup(
      <div>{ids.map(id => <Day1BackgroundButton key={id} testId={id} dialogOpen onClick={noop}>{id}</Day1BackgroundButton>)}</div>,
    );
    ids.forEach(id => expect(html).toContain(`data-testid="day1-background-${id}" disabled=""`));

    const action = vi.fn();
    const blocked = Day1BackgroundButton({ testId: 'probe', dialogOpen: true, onClick: action, children: 'probe' });
    blocked.props.onClick();
    expect(action).not.toHaveBeenCalled();
    const enabled = Day1BackgroundButton({ testId: 'probe', dialogOpen: false, onClick: action, children: 'probe' });
    enabled.props.onClick();
    expect(action).toHaveBeenCalledTimes(1);
  });
});
