import { useState } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, LineChart, Line, Legend } from 'recharts';
import type { Variant } from '../../types';
import { average } from '../../utils/offerPricing';
import { money } from './rebuild/detailFormatters';
import { currentBars, weeklyHistory } from './priceChartData';

export function PriceChart({ variants }: { variants: Variant[] }) {
  const [original, setOriginal] = useState(false);
  const [selectedCurrency, setSelectedCurrency] = useState('');
  const [showUnavailable, setShowUnavailable] = useState(true);
  const currencies = [...new Set(variants.flatMap(v => [v.currency, ...v.points.map(p => p.currency || v.currency)]).filter(Boolean))].sort();
  const currency = original ? (currencies.includes(selectedCurrency) ? selectedCurrency : currencies[0] || 'CNY') : 'CNY';
  const bars = currentBars(variants, currency, original);
  const data = weeklyHistory(variants, currency, original);
  const avg = average(bars.map(bar => bar.price));
  const points = variants.flatMap(v => v.points);
  const outCount = points.filter(p => p.in_stock === false && !p.delisted).length;
  const delistedCount = points.filter(p => p.delisted === true).length;
  const anomalyCount = points.filter(p => p.anomaly?.exclude_from_aggregate).length;
  const hasTrend = data.some(row => row.active !== null || row.soldOut !== null || row.delisted !== null);
  return (
    <div className="rd-charts" data-guide="prices-history-chart">
      <div className="rd-chart-toolbar">
        <div className="rd-chart-controls" role="group" aria-label="图表币种">
          <button type="button" aria-pressed={!original} onClick={() => setOriginal(false)}>CNY</button>
          <button type="button" aria-pressed={original} onClick={() => setOriginal(true)}>原币</button>
        </div>
        {original && <label className="rd-currency-label">原币种走势 <select aria-label="选择原币币种" value={currency} onChange={event => setSelectedCurrency(event.target.value)}>{currencies.map(code => <option key={code}>{code}</option>)}</select></label>}
      </div>
      <section aria-label="当前在售报价图">
        <h3>当前在售单支价格（{currency}）</h3>
        {bars.length ? <>
          <ResponsiveContainer width="100%" height={Math.max(220, bars.length * 44)}>
            <BarChart data={bars} layout="vertical" margin={{ left: 0, right: 24, top: 18, bottom: 8 }}>
              <CartesianGrid stroke="#E8E0D6" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 11 }} />
              <Tooltip formatter={value => [money(Number(value), currency) + '/支', '价格']} labelFormatter={(_, payload) => payload[0]?.payload?.product || ''} />
              {avg !== null && <ReferenceLine x={avg} stroke="#B87A3A" strokeDasharray="4 4" label={{ value: '均价', fill: '#B87A3A', fontSize: 11 }} />}
              <Bar dataKey="price" name="在售单支价" fill="#7A1F2E" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <p className="rd-note">由低到高排列 · 虚线为当前在售报价均价 {money(avg, currency)}/支。仅统计在售且 CNY 价格、盒规有效的报价；原币模式另需该币种原始价格有效。</p>
        </> : <p className="rd-chart-empty">暂无符合条件的当前在售报价。</p>}
      </section>
      <section aria-label="每周价格趋势">
        <div className="rd-chart-toolbar">
          <h3>历史单支价格趋势（{currency}）</h3>
          <label className="rd-note"><input type="checkbox" checked={showUnavailable} onChange={event => setShowUnavailable(event.target.checked)} /> 显示售罄 / 下架历史</label>
        </div>
        {hasTrend ? <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={{ left: 0, right: 20, top: 8, bottom: 8 }}>
            <CartesianGrid stroke="#E8E0D6" strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={35} />
            <YAxis tick={{ fontSize: 10 }} width={55} />
            <Tooltip formatter={(value, name) => [money(Number(value), currency) + '/支', name]} labelFormatter={label => `周起始：${label}`} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="linear" dataKey="active" name="在售来源均线" stroke="#7A1F2E" strokeWidth={2.5} dot={{ r: 3 }} connectNulls={false} />
            {showUnavailable && <Line type="linear" dataKey="soldOut" name="售罄历史均线（不参与在售统计）" stroke="#A75B27" strokeOpacity={0.55} strokeDasharray="5 5" dot={{ r: 2 }} connectNulls={false} />}
            {showUnavailable && <Line type="linear" dataKey="delisted" name="下架历史均线（不参与在售统计）" stroke="#8A7E6E" strokeOpacity={0.45} strokeDasharray="2 5" dot={{ r: 2 }} connectNulls={false} />}
          </LineChart>
        </ResponsiveContainer> : <p className="rd-chart-empty">所选范围暂无可绘制的有效历史价格。</p>}
        <p className="rd-note">按 UTC 周一分周，每个来源 × 盒规 × 商品链接取周内最后一次快照；先在来源内平均，再对来源等权平均。状态取自当时快照，不套用当前状态。无快照周不补值，空缺处断线；快照经过去重，均线不是每日市场均价。</p>
        <p className="rd-note">本范围保留 {outCount} 条售罄、{delistedCount} 条下架记录；{anomalyCount} 条异常记录排除统计。缺少有效价格或盒规的记录不绘制价格，售罄与下架仅作历史参考。</p>
        <p className="rd-note">CNY 使用快照保存的折算值；原币按快照币种分别展示，不合并不同币种。历史实际折算汇率与日期未保存，来源当前参考汇率见报价表。</p>
        {data.length > 0 && <details className="rd-weekly-data"><summary>查看每周统计数据</summary><div className="rd-weekly-list">
          {data.map(row => <div key={row.date}><time>{row.date}</time><span>在售 {money(row.active, currency)}/支 · {row.sourceCount} 个来源</span><span>售罄 {money(row.soldOut, currency)}/支</span><span>下架 {money(row.delisted, currency)}/支</span></div>)}
        </div></details>}
      </section>
    </div>
  );
}
