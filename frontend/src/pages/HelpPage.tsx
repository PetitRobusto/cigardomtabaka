import { useEffect, useState } from 'react';
import { BookOpen, ExternalLink, Play } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { MANUAL_CHAPTERS, type ManualChapter } from '../features/guides/guideContent';
import { usePageMeta } from '../hooks/usePageMeta';
import { replayGuide } from '../api';

const quickStartOrder = ['账户入账', '汇率换汇', '采购到货', '库存', '销售', '出库与收款', '对账', '月利润'];

export default function HelpPage() {
  const { setMeta } = usePageMeta();
  const navigate = useNavigate();
  const [chapterId, setChapterId] = useState('quickstart');
  const [message, setMessage] = useState('');
  const chapter = MANUAL_CHAPTERS.find(item => item.id === chapterId) || MANUAL_CHAPTERS[0];
  useEffect(() => { setMeta({ title: '使用手册', breadcrumbs: [{ label: '首页', to: '/' }, { label: '使用手册' }] }); }, [setMeta]);

  const openFeature = () => navigate(chapter.route);
  const playTour = async () => {
    if (!chapter.tourStepId) { setMessage('本章暂无页面引导'); return; }
    try {
      await replayGuide();
      navigate(chapter.route, { state: { guideTourId: chapter.tourStepId } });
    } catch (error) { setMessage(error instanceof Error ? error.message : '引导重播失败，请稍后重试'); }
  };

  return <div className="animate-fade-in">
    <header className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-[11px] font-bold uppercase tracking-[.15em] text-gold">帮助中心 · 内部手册</p><h1 className="mt-1 font-display text-3xl font-semibold tracking-tight">让每一步，都有答案。</h1><p className="mt-2 text-sm text-muted">查找工作流程、字段解释和常用操作。</p></div><button type="button" onClick={playTour} className="inline-flex items-center justify-center gap-2 rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white"><Play className="h-4 w-4" />播放本页引导</button></header>
    {message && <p role="status" className="mb-4 rounded border border-border bg-white px-4 py-3 text-sm text-muted">{message}</p>}
    <div className="grid gap-7 lg:grid-cols-[240px_1fr]">
      <aside className="hidden border-r border-border pr-5 lg:block"><ChapterNav chapters={MANUAL_CHAPTERS} active={chapterId} onSelect={setChapterId} /></aside>
      <div className="min-w-0"><label className="sr-only" htmlFor="manual-chapter">选择手册章节</label><select id="manual-chapter" value={chapterId} onChange={event => setChapterId(event.target.value)} className="mb-5 w-full rounded border border-border bg-white px-3 py-2.5 text-sm lg:hidden">{MANUAL_CHAPTERS.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select><ChapterContent chapter={chapter} onOpen={openFeature} onPlay={playTour} />{chapter.id === 'quickstart' && <div className="mt-6 rounded border border-border bg-white p-5"><h2 className="font-display text-lg font-semibold">推荐顺序</h2><div className="mt-3 flex flex-wrap gap-2">{quickStartOrder.map((item, index) => <span key={item} className="rounded-full bg-accent-light px-3 py-1.5 text-xs text-fg">{index + 1}. {item}</span>)}</div></div>}</div>
    </div>
  </div>;
}

function ChapterNav({ chapters, active, onSelect }: { chapters: readonly ManualChapter[]; active: string; onSelect: (id: string) => void }) { return <nav aria-label="手册章节" className="space-y-1"><p className="mb-2 px-3 text-[11px] font-bold uppercase tracking-wider text-gold">开始使用</p>{chapters.filter(item => item.category === 'quickstart').map(item => <ChapterButton key={item.id} chapter={item} active={active === item.id} onSelect={onSelect} />)}<p className="mb-2 mt-6 px-3 text-[11px] font-bold uppercase tracking-wider text-gold">功能参考</p>{chapters.filter(item => item.category === 'reference').map(item => <ChapterButton key={item.id} chapter={item} active={active === item.id} onSelect={onSelect} />)}</nav>; }
function ChapterButton({ chapter, active, onSelect }: { chapter: ManualChapter; active: boolean; onSelect: (id: string) => void }) { return <button type="button" onClick={() => onSelect(chapter.id)} className={`block w-full rounded px-3 py-2.5 text-left text-sm ${active ? 'bg-accent-light font-semibold text-accent' : 'text-muted hover:bg-accent-light'}`}>{chapter.title}</button>; }
function ChapterContent({ chapter, onOpen, onPlay }: { chapter: ManualChapter; onOpen: () => void; onPlay: () => void }) { return <article className="max-w-3xl"><p className="text-[11px] font-bold uppercase tracking-[.15em] text-gold">{chapter.category === 'quickstart' ? '快速开始' : '功能参考'}</p><h2 className="mt-2 font-display text-3xl font-semibold">{chapter.title}</h2><p className="mt-3 text-sm leading-7 text-muted">{chapter.summary}</p><div className="mt-6 space-y-4">{chapter.sections.map(section => <section key={section.title} className="rounded border border-border bg-white p-5"><h3 className="font-display text-lg font-semibold">{section.title}</h3>{section.paragraphs.map(paragraph => <p key={paragraph} className="mt-2 text-sm leading-7 text-muted">{paragraph}</p>)}</section>)}</div><div className="mt-6 flex flex-wrap gap-3"><button type="button" onClick={onOpen} className="inline-flex items-center gap-2 rounded border border-border bg-white px-4 py-2.5 text-sm font-semibold"><ExternalLink className="h-4 w-4" />打开功能</button><button type="button" onClick={onPlay} className="inline-flex items-center gap-2 rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white"><BookOpen className="h-4 w-4" />播放本页引导</button></div></article>; }
