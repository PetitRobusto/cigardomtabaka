import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { fetchAccessNotes, fetchAccessDetail, type AccessPage } from '../../api/privnoteAccess';

const types: Record<string, string> = { inventory: '库存', payment: '收款', message: '消息', quote: '报价单' };
const events: Record<string, string> = {
  open: '成功打开', password_required: '需要密码', password_failed: '密码错误',
  expired: '已过期', destroyed: '已销毁', closed: '已关闭', error: '打开失败',
  qr_open: '放大收款二维码', copy_card: '复制卡号', copy_account: '复制收款账号', submission: '提交凭证 · 待核实',
};
const button = 'inline-flex items-center justify-center gap-1.5 rounded border border-border bg-white px-3 py-2 text-xs font-semibold hover:border-gold disabled:opacity-40';
const cell = 'block px-4 py-2 md:table-cell md:py-3';
const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const date = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—';

function Pagination({ data, setPage }: { data: AccessPage; setPage: (page: number) => void }) {
  return <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-cream px-4 py-3 text-xs text-muted">
    <span>共 {data.count} 条 · 第 {data.page} / {data.pages} 页</span>
    <div className="flex gap-2"><button className={button} disabled={data.page <= 1} onClick={() => setPage(data.page - 1)}>上一页</button><button className={button} disabled={data.page >= data.pages} onClick={() => setPage(data.page + 1)}>下一页</button></div>
  </div>;
}
function Retry({ error, retry }: { error: Error; retry: () => void }) {
  return <div role="alert" className="p-8 text-center text-sm"><p>{error.message}</p><button className={`${button} mt-3`} onClick={retry}><RefreshCw size={13} />重试</button></div>;
}

function Detail({ token, back }: { token: string; back: () => void }) {
  const [audience, setAudience] = useState('customer');
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ['privnote-access', token, audience, page], queryFn: () => fetchAccessDetail(token, audience, page), retry: false });
  const data = query.data;
  return <div>
    <button className={`${button} mb-4`} onClick={back}><ArrowLeft size={14} />返回链接列表</button>
    <section className="overflow-hidden rounded-lg border border-border bg-white">
      {query.isPending ? <p role="status" className="p-8 text-center text-sm text-muted">正在加载访问记录…</p> : query.isError ? <Retry error={query.error} retry={() => void query.refetch()} /> : data && <>
        <header className="border-b border-border p-5">
          <div className="flex flex-wrap items-center gap-3"><h2 className="font-display text-lg font-semibold">{data.note.title}</h2><span className="rounded-full bg-accent-light px-2 py-1 text-xs text-muted">{types[data.note.note_type]}</span></div>
          <p className="mt-1 font-mono text-xs text-muted">{data.note.token} · 创建于 {date(data.note.created_at)}</p>
          <p className="mt-4 text-sm leading-7">近 {data.retention_days} 天 · 成功打开 <b>{data.summary.opens}</b> 次 · 匿名浏览器约 <b>{data.summary.visitors}</b> 个 · 回访 <b>{data.summary.revisits}</b> 次</p>
          <p className="text-xs leading-6 text-muted">最近成功打开：{date(data.summary.last_opened_at)} · 历史累计打开 {data.note.view_count} 次（含员工等访问，独立于保留期统计）</p>
        </header>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-cream px-4 py-3">
          <label className="text-xs">记录范围 <select className="ml-2 rounded border border-border bg-white px-2 py-2" value={audience} onChange={event => { setAudience(event.target.value); setPage(1); }}><option value="customer">仅客户</option><option value="all">全部（含员工与疑似机器人）</option></select></label>
          <span className="text-xs text-muted">时间：{zone}</span>
        </div>
        {!data.results.length ? <p className="p-8 text-center text-sm leading-7 text-muted">当前范围内暂无近 {data.retention_days} 天明细。<br />历史累计次数保留，未采集或已清理的 IP 与设备无法补回。</p> : <table className="block w-full text-left text-xs md:table">
          <thead className="hidden border-b border-border text-muted md:table-header-group"><tr><th className={cell}>时间</th><th className={cell}>访客</th><th className={cell}>设备与打开环境</th><th className={cell}>IP</th><th className={cell}>结果 / 操作</th></tr></thead>
          <tbody className="block md:table-row-group">{data.results.map(entry => <tr key={entry.id} className="block border-b border-border py-2 last:border-0 md:table-row md:py-0">
            <td className={`${cell} font-mono text-muted`}>{date(entry.created_at)}</td>
            <td className={cell}>{entry.actor === 'customer' ? <><span>{entry.visitor ? `访客 ${entry.visitor}` : '未识别浏览器'}</span>{entry.event === 'open' && entry.visitor && <span className="ml-2 text-muted md:ml-0 md:block">{entry.is_revisit ? '回访 · 估算' : '首次打开 · 近保留期'}</span>}</> : entry.actor === 'staff' ? '员工访问' : '疑似机器人'}</td>
            <td className={cell}>{entry.device} · {entry.browser}</td>
            <td className={`${cell} break-all font-mono text-muted`}><span className="md:hidden">IP：</span>{entry.ip || '未获取'}</td>
            <td className={cell}><span className={`inline-block rounded-full px-2 py-1 ${entry.event === 'open' ? 'bg-green-50 text-green-800' : ['password_failed', 'error'].includes(entry.event) ? 'bg-orange-50 text-orange-800' : 'bg-accent-light text-fg'}`}>{events[entry.event] || entry.event}</span></td>
          </tr>)}</tbody>
        </table>}
        <Pagination data={data} setPage={setPage} />
        <p className="border-t border-border px-4 py-3 text-xs leading-6 text-muted">访客编号仅在本链接内有效。Cookie 被清理或更换浏览器会影响估算；首次与回访仅指保留期内的成功打开。提交凭证不代表已收款。</p>
      </>}
    </section>
  </div>;
}

/** Open Design: privnote-access-records.html; one list and a compact detail. */
export default function AccessRecords({ initialToken = '' }: { initialToken?: string }) {
  const [token, setToken] = useState(initialToken);
  const [q, setQ] = useState('');
  const [type, setType] = useState('');
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ['privnote-access-notes', q, type, page], queryFn: () => fetchAccessNotes(q, type, page), enabled: !token, retry: false });
  if (token) return <Detail key={token} token={token} back={() => setToken('')} />;
  return <section className="overflow-hidden rounded-lg border border-border bg-white">
    <div className="flex flex-wrap gap-3 border-b border-border bg-cream p-4">
      <input aria-label="搜索标题或链接编号" placeholder="搜索标题或链接编号…" className="min-w-0 flex-1 rounded border border-border bg-white px-3 py-2 text-sm" value={q} onChange={event => { setQ(event.target.value); setPage(1); }} />
      <select aria-label="链接类型" className="rounded border border-border bg-white px-3 py-2 text-sm" value={type} onChange={event => { setType(event.target.value); setPage(1); }}><option value="">全部类型</option>{Object.entries(types).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <button aria-label="刷新访问记录" className={button} onClick={() => void query.refetch()}><RefreshCw size={14} />刷新</button>
    </div>
    <p className="border-b border-border px-4 py-2 text-xs text-muted">时间：{zone} · 最近打开统计范围：近 {query.data?.retention_days ?? 30} 天</p>
    {query.isPending ? <p role="status" className="p-8 text-center text-sm text-muted">正在加载链接…</p> : query.isError ? <Retry error={query.error} retry={() => void query.refetch()} /> : query.data && <>
      {!query.data.results.length ? <p className="p-8 text-center text-sm text-muted">暂无符合条件的链接</p> : <table className="block w-full text-left text-xs md:table">
        <thead className="hidden border-b border-border text-muted md:table-header-group"><tr><th className={cell}>链接 / 类型</th><th className={cell}>创建时间</th><th className={cell}>历史累计打开</th><th className={cell}>最近成功打开</th><th className={cell}>操作</th></tr></thead>
        <tbody className="block md:table-row-group">{query.data.results.map(note => <tr key={note.token} className="block border-b border-border py-2 last:border-0 md:table-row md:py-0">
          <td className={cell}><span className="font-semibold">{note.title}</span><span className="mt-1 block font-mono text-muted">{types[note.note_type]} · {note.token}</span></td>
          <td className={`${cell} font-mono text-muted`}><span className="md:hidden">创建于 </span>{date(note.created_at)}</td>
          <td className={`${cell} font-mono`}><span className="md:hidden">历史累计打开 </span>{note.view_count} 次</td>
          <td className={`${cell} font-mono text-muted`}><span className="md:hidden">最近打开 </span>{note.last_opened_at ? date(note.last_opened_at) : '暂无明细'}</td>
          <td className={cell}><button className={button} onClick={() => setToken(note.token)}>查看记录</button></td>
        </tr>)}</tbody>
      </table>}
      <Pagination data={query.data} setPage={setPage} />
    </>}
  </section>;
}
