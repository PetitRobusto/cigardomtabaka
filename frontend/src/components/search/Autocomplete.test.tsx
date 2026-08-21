import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { SearchCigarResult } from '../../types';
import CustomerAutocomplete from './CustomerAutocomplete';
import { CigarAutocompleteResult } from './CigarAutocomplete';

const cigar: SearchCigarResult = {
  id: 7,
  name: 'D 4',
  english_name: 'Serie D No. 4',
  brand: 'Partagás',
  brand_cn: '帕特加斯',
  release_type: '',
  release_type_cn: '',
  is_regular: true,
  vitola: 'Robusto',
  length: 124,
  ring_gauge: 50,
  thumb_url: null,
  packaging_sizes: [25],
  stock_qty: 50,
  box_options: [{ box_size: 25, available_boxes: 2 }],
  available_sticks: 0,
  batches: [],
};

describe('可复用联想搜索', () => {
  it('客户模块支持受控自由文本和已选客户档案', () => {
    const html = renderToStaticMarkup(<CustomerAutocomplete value={{ customerId: 3, name: '王先生' }} onChange={() => {}} />);
    expect(html).toContain('客户名称');
    expect(html).toContain('王先生');
    expect(html).toContain('已关联客户档案');
  });

  it('产品结果统一展示中文品牌、英文原名和常规款标签', () => {
    const html = renderToStaticMarkup(<CigarAutocompleteResult cigar={cigar} />);
    expect(html).toContain('帕特加斯 D 4');
    expect(html).toContain('Partagás Serie D No. 4');
    expect(html).toContain('常规款');
    expect(html).toContain('25支×2盒');
  });

  it('特别款优先展示具体款型', () => {
    const html = renderToStaticMarkup(<CigarAutocompleteResult cigar={{ ...cigar, is_regular: false, release_type_cn: '限量版系列' }} />);
    expect(html).toContain('限量版系列');
    expect(html).not.toContain('常规款');
  });
});
