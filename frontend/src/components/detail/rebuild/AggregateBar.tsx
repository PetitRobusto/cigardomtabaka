import { money } from './detailFormatters';

export function AggregateBar({ avg, min, max, count }: {
  avg: number | null; min: number | null; max: number | null; count: number;
}) {
  return (
    <section className="rd-aggregate" aria-label="在售价格汇总">
      <div><small>在售均价 / 支</small><strong>{money(avg)}</strong></div>
      <div><small>最低价 / 支</small><strong>{money(min)}</strong></div>
      <div><small>最高价 / 支</small><strong>{money(max)}</strong></div>
      <div><small>当前有效报价</small><strong>{count}</strong></div>
      <aside>按来源 × 盒规 × 商品链接的在售报价等权平均。仅含有效 CNY 价格和盒规；售罄、下架、无效及排除统计的异常报价保留展示。</aside>
    </section>
  );
}
