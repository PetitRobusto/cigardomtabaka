import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import DividendAction, { dividendAccountOptions, validateDividendDraft } from './DividendAction';

describe('分红动作卡 SSR 契约', () => {
  it('显示草稿编辑、preview warning 和 acknowledgement 后确认边界', () => {
    const html = renderToStaticMarkup(<DividendAction {...({ accounts: [{ id: 1, name: '人民币账户', currency: 'CNY', is_active: true }], draft: { id: 20, status: 'draft', version: 1, total_cny: '1000.00' }, preview: { warning_code: 'retained_earnings', warning: '确认后将减少未分配利润', warning_fingerprint: 'fp-1' }, warningAcknowledged: false, onCreate: () => undefined, onUpdate: () => undefined, onPreview: () => undefined, onConfirm: () => undefined } as never)} />);
    expect(html).toContain('预览');
    expect(html).toContain('确认分红');
    expect(html).toContain('确认后将减少未分配利润');
    expect(html).toMatch(/warning|确认.*提示|我已确认/i);
  });

  it('分红预览校验：dirty 草稿不可预览、同账户无效、不同账户有效', () => {
    expect(validateDividendDraft({ draftDirty: true, accountA: 1, accountB: 2 })).toMatchObject({ ok: false });
    expect(validateDividendDraft({ draftDirty: false, accountA: 1, accountB: 1 })).toMatchObject({ ok: false });
    expect(validateDividendDraft({ draftDirty: false, accountA: 1, accountB: 2 })).toMatchObject({ ok: true });
  });

  it('合伙人账户选项：对侧已选账户不可再次选择', () => {
    const options = dividendAccountOptions([
      { id: 1, name: '账户 A', currency: 'CNY', is_active: true },
      { id: 2, name: '账户 B', currency: 'CNY', is_active: true },
    ], 1);

    expect(options.find(option => option.account.id === 1)).toMatchObject({ disabled: true });
    expect(options.find(option => option.account.id === 2)).toMatchObject({ disabled: false });
  });
});
