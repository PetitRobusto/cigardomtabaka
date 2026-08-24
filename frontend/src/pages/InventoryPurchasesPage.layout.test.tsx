import { renderToStaticMarkup } from 'react-dom/server';
import type { PurchaseAction } from '../types';
import { describe, expect, it } from 'vitest';
import { DetailItems, DraftEditor, ModalFrame } from './InventoryPurchasesPage';

describe('采购单编辑 modal 布局契约', () => {
  it('编辑器使用动态视口高度、固定头尾并只滚动正文', () => {
    const html = renderToStaticMarkup(
      <ModalFrame editor onClose={() => {}}>
        <DraftEditor
          draft={{ id: null, version: null, supplier: null, businessDate: '2026-08-24', note: '', items: [] }}
          busy={false}
          error=""
          onChange={() => {}}
          onClose={() => {}}
          onSave={() => {}}
        />
      </ModalFrame>,
    );

    expect(html).toContain('h-dvh');
    expect(html).toContain('sm:h-[94dvh]');
    expect(html).toContain('overflow-hidden');
    expect(html).toContain('data-purchase-modal-body="scroll"');
    expect(html).toContain('min-h-0 flex-1 overflow-y-auto overscroll-contain');
  });

  it('目录有盒规时使用 select 而不是自由数字输入', () => {
    const html = renderToStaticMarkup(
      <DraftEditor
        draft={{
          id: null,
          version: null,
          supplier: null,
          businessDate: '2026-08-24',
          note: '',
          items: [{
            cigarId: 7,
            cigarName: 'D 4',
            cigarEnglishName: 'Serie D No. 4',
            brand: 'Partagás',
            releaseTypeCn: '',
            brandCn: '帕特加斯',
            isRegular: true,
            packagingSizes: [10, 25],
            boxSize: '25',
            boxQuantity: '1',
            unitPriceRubPerBox: '25000',
          }],
        }}
        busy={false}
        error=""
        onChange={() => {}}
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    expect(html).toContain('<select');
    expect(html).toContain('10 支/盒');
    expect(html).toContain('25 支/盒');
    expect(html).not.toContain('Partagás D 4');
    expect(html).toContain('帕特加斯 D 4');
  });
  it('已保存采购单的商品主标题也使用完整中文品名', () => {
    const purchase = {
      items: [{
        cigar_id: 7,
        cigar_name: 'D 4',
        cigar_english_name: 'Serie D No. 4',
        brand: 'Partagás',
        brand_cn: '帕特加斯',
        is_regular: true,
        box_size: 25,
        box_quantity: 1,
        quantity: 25,
        unit_price_rub_per_box: '25000',
      }],
    } as PurchaseAction;
    const html = renderToStaticMarkup(<DetailItems purchase={purchase} />);

    expect(html).toContain('帕特加斯 D 4');
    expect(html).not.toContain('Partagás D 4');
  });
});
