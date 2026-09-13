import { ExternalLink } from 'lucide-react';
import type { Variant } from '../../../types';
import { eligibleVariant, offerKey, positive, unitPrice } from '../../../utils/offerPricing';
import { invalidReason, money, statusLabels, statusOf, timestamp } from './detailFormatters';

function ExchangeNote({ v }: { v: Variant }) {
  return <small className="rd-exchange">
    {positive(v.source_exchange_rate) && v.source_currency
      ? `来源当前参考：1 ${v.source_currency} = ${v.source_exchange_rate} CNY`
      : '来源未提供参考汇率'}
  </small>;
}

export function OfferComparison({ variants }: { variants: Variant[] }) {
  const values = variants.filter(eligibleVariant).map(v => unitPrice(v.current_price_cny, v.box_size)!);
  const min = values.length ? Math.min(...values) : null;
  return (
    <section className="rd-offers" data-guide="prices-history-table">
      <header><h2>来源 × 盒规报价</h2><span>{variants.length} 条报价</span></header>
      <div className="of-head" aria-hidden="true">
        {['来源', '款式名称', '盒规', '原币盒价', 'CNY 盒价', 'CNY 单支价', '最近抓取', '状态 / 操作'].map(label => <span key={label}>{label}</span>)}
      </div>
      {!variants.length && <p className="rd-note p-5">暂无来源报价。</p>}
      {variants.map(v => {
        const status = statusOf(v);
        const perStick = unitPrice(v.current_price_cny, v.box_size);
        const best = min !== null && perStick === min && eligibleVariant(v);
        return (
          <article className={`of-row ${status}${best ? ' best' : ''}`} key={offerKey(v)} aria-label={`${v.source_name} ${v.box_label} ${statusLabels[status]}`}>
            <div className="of-source" data-label="来源"><b>{v.source_short_name || v.source_name}</b>{v.source_short_name && <small>{v.source_name}</small>}{v.record_count != null && <small>{v.record_count} 条历史记录</small>}</div>
            <div className="of-name" data-label="款式名称">{v.product_name || v.scraped_name || '来源未提供名称'}</div>
            <div data-label="盒规">{v.box_label || '未知盒规'}</div>
            <div className="of-price" data-label="原币盒价"><span>{money(v.current_price, v.currency)}</span><ExchangeNote v={v} /></div>
            <div className="of-price" data-label="CNY 盒价"><span>{money(v.current_price_cny)}</span></div>
            <div className="of-price of-unit" data-label="CNY 单支价"><span>{money(perStick)} /支</span>{best && <small className="rd-best">最低在售价</small>}</div>
            <div className="of-time" data-label="最近抓取"><time dateTime={v.scraped_at}>{timestamp(v.scraped_at)}</time></div>
            <div className="rd-row-status" data-label="状态 / 操作">
              <em className={`pill ${status}`}>{statusLabels[status]}</em>
              {v.url && <a className="rd-source-link" href={v.url} target="_blank" rel="noreferrer" aria-label={`查看${v.source_name}来源，核验报价`}><ExternalLink size={13} /></a>}
              {status === 'out' && <small>当前售罄，不参与均价</small>}
              {status === 'delisted' && <small>已下架，仅保留记录</small>}
              {invalidReason(v) && <small>{invalidReason(v)}</small>}
              {!positive(v.current_price) && <small>来源原币价格缺失或无效</small>}
              {v.anomaly && <><em className="pill anomaly">{v.anomaly.label}</em><small>{v.anomaly.reason}</small><small>{v.anomaly.exclude_from_aggregate ? '已排除统计。' : ''}请打开来源核验，并向管理员反馈{v.snapshot_id ? `记录 #${v.snapshot_id}` : '此报价'}。</small></>}
            </div>
          </article>
        );
      })}
      <p className="rd-note rd-exchange-note">原币价格保留原始值，CNY 仅用于统一比较展示。来源参考汇率是当前配置，未必等于快照实际折算汇率；后端未保存历史折算汇率及其日期，不能据此还原历史成本。</p>
    </section>
  );
}
