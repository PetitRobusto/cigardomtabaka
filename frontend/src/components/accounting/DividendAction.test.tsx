import type { ComponentProps } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { FundAccount } from '../../types';
import DividendAction from './DividendAction';
import { dividendAccountOptions, dividendActionResetKey, validateDividendDraft } from './DividendAction.logic';

describe('分红动作卡 SSR 契约', () => {
  it('显示草稿编辑、preview warning 和 acknowledgement 后确认边界', () => {
    // 预览夹具与后端结构化 warning 契约保持一致。
    const props = {
      accounts: [{ id: 1, name: '人民币账户', currency: 'CNY', custodian_id: null, is_active: true }],
      draft: { id: 20, status: 'draft', version: 1, total_cny: '1000.00' },
      preview: {
        retained_earnings_cny: '500.00',
        requested_cny: '1000.00',
        warning: {
          code: 'retained_earnings_exceeded',
          retained_earnings_cny: '500.00',
          requested_cny: '1000.00',
          fingerprint: 'fp-1',
        },
        warning_fingerprint: 'fp-1',
      },
      warningAcknowledged: false,
      onCreate: () => undefined,
      onUpdate: () => undefined,
      onPreview: () => undefined,
      onConfirm: () => undefined,
    } satisfies ComponentProps<typeof DividendAction>;
    const html = renderToStaticMarkup(<DividendAction {...props} />);
    expect(html).toContain('预览');
    expect(html).toContain('确认分红');
    expect(html).toContain('超过当前未分配利润');
    expect(html).toMatch(/warning|确认.*提示|我已确认/i);
  });

  it('分红预览校验：dirty 草稿不可预览、同账户无效、不同账户有效', () => {
    expect(validateDividendDraft({ draftDirty: true, accountA: 1, accountB: 2 })).toMatchObject({ ok: false });
    expect(validateDividendDraft({ draftDirty: false, accountA: 1, accountB: 1 })).toMatchObject({ ok: false });
    expect(validateDividendDraft({ draftDirty: false, accountA: 1, accountB: 2 })).toMatchObject({ ok: true });
  });

  it('合伙人账户选项：对侧已选账户不可再次选择', () => {
    const options = dividendAccountOptions([
      { id: 1, name: '账户 A', currency: 'CNY', custodian_id: null, is_active: true },
      { id: 2, name: '账户 B', currency: 'CNY', custodian_id: null, is_active: true },
    ] satisfies FundAccount[], 1);

    expect(options.find(option => option.account.id === 1)).toMatchObject({ disabled: true });
    expect(options.find(option => option.account.id === 2)).toMatchObject({ disabled: false });
  });

  // key 语义测试覆盖外部更新同步，同时保证普通重渲染不重置输入。
  it('外部草稿语义变化才会触发内部表单重置', () => {
    const draft = { id: 20, status: 'draft', version: 1, total_cny: '1000.00' };
    expect(dividendActionResetKey(draft, 'fp-1', '2026-08-16', false))
      .toBe(dividendActionResetKey({ ...draft }, 'fp-1', '2026-08-16', false));
    expect(dividendActionResetKey(draft, 'fp-2', '2026-08-16', false))
      .not.toBe(dividendActionResetKey(draft, 'fp-1', '2026-08-16', false));
  });
});
