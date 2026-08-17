import { useCallback, useEffect, useRef, useState } from 'react';
import { Day1StatusNotice } from './helpState';
import { day1StatusErrorState, day1StatusLoadingState, day1StatusReadyState, type Day1StatusState } from './helpState.helpers';
import { BookOpen, ExternalLink, Play } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { MANUAL_CHAPTERS, type ManualChapter } from '../features/guides/guideContent';
import { usePageMeta } from '../hooks/usePageMeta';
import { manualTourDecision } from '../features/guides/manualTour';
import { tourStepRoute, tourStepsForRoute } from '../features/guides/guideInteractions';
import { fetchDay1State } from '../api';
import { invalidateLatestRequest, runLatestRequest } from '../utils/latestRequest';

const quickStartOrder = ['账户入账', '汇率换汇', '采购到货', '库存', '销售', '出库与收款', '对账', '月利润'];

export default function HelpPage() {
  const { setMeta } = usePageMeta();
  const navigate = useNavigate();
  const [chapterId, setChapterId] = useState('quickstart');
  const [message, setMessage] = useState('');
  const [day1State, setDay1State] = useState<Day1StatusState>(day1StatusLoadingState());
  const requestSequence = useRef({ current: 0 });
  const chapter = MANUAL_CHAPTERS.find(item => item.id === chapterId) || MANUAL_CHAPTERS[0];
  useEffect(() => { setMeta({ title: '使用手册', breadcrumbs: [{ label: '首页', to: '/' }, { label: '使用手册' }] }); }, [setMeta]);
  const requestDay1Status = useCallback(() => {
    void runLatestRequest({
      sequence: requestSequence.current,
      request: fetchDay1State,
      onSuccess: data => setDay1State(day1StatusReadyState(data.status)),
      onError: () => setDay1State(day1StatusErrorState()),
    });
  }, []);
  const loadDay1Status = useCallback(() => {
    setDay1State(day1StatusLoadingState());
    requestDay1Status();
  }, [requestDay1Status]);
  useEffect(() => {
    const sequence = requestSequence.current;
    // 初始状态已经是 loading，首屏请求只处理异步完成结果。
    requestDay1Status();
    return () => invalidateLatestRequest(sequence);
  }, [requestDay1Status]);

  const day1Status = day1State.status === "ready" ? day1State.day1Status : undefined;
  const decideChapter = () => manualTourDecision(chapter, { day1Status });
  const openFeature = () => {
    const decision = decideChapter();
    if (decision.kind === 'unavailable') { navigate(chapter.route); return; }
    navigate(decision.destination.route, { state: decision.destination.state });
  };
  const openStep = (stepId: string) => {
    const route = tourStepRoute(stepId);
    if (!route) { setMessage('这一步暂时没有可用的页面引导。'); return; }
    setMessage('');
    navigate(route, { state: { guideTourId: stepId } });
  };
  const playTour = () => {
    const decision = decideChapter();
    if (decision.kind === 'unavailable') { setMessage(decision.message); return; }
    navigate(decision.destination.route, { state: decision.destination.state });
  };

  return <div className="animate-fade-in">
    <header className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-[11px] font-bold uppercase tracking-[.15em] text-gold">帮助中心 · 内部手册</p><h1 className="mt-1 font-display text-3xl font-semibold tracking-tight">让每一步，都有答案。</h1><p className="mt-2 text-sm text-muted">查找工作流程、字段解释和常用操作。</p></div><button type="button" onClick={playTour} className="inline-flex items-center justify-center gap-2 rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white"><Play className="h-4 w-4" />播放本页引导</button></header>
    <Day1StatusNotice state={day1State} onRetry={loadDay1Status} />
    {message && <p role="status" className="mb-4 rounded border border-border bg-white px-4 py-3 text-sm text-muted">{message}</p>}
    <div className="grid gap-7 lg:grid-cols-[240px_1fr]">
      <aside className="hidden border-r border-border pr-5 lg:block"><ChapterNav chapters={MANUAL_CHAPTERS} active={chapterId} onSelect={setChapterId} /></aside>
      <div className="min-w-0"><label className="sr-only" htmlFor="manual-chapter">选择手册章节</label><select id="manual-chapter" value={chapterId} onChange={event => setChapterId(event.target.value)} className="mb-5 w-full rounded border border-border bg-white px-3 py-2.5 text-sm lg:hidden">{MANUAL_CHAPTERS.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select><ChapterContent chapter={chapter} onOpen={openFeature} onPlay={playTour} onOpenStep={openStep} />{chapter.id === 'quickstart' && <div className="mt-6 rounded border border-border bg-white p-5"><h2 className="font-display text-lg font-semibold">推荐顺序</h2><div className="mt-3 flex flex-wrap gap-2">{quickStartOrder.map((item, index) => <span key={item} className="rounded-full bg-accent-light px-3 py-1.5 text-xs text-fg">{index + 1}. {item}</span>)}</div></div>}</div>
    </div>
  </div>;
}

function ChapterNav({ chapters, active, onSelect }: { chapters: readonly ManualChapter[]; active: string; onSelect: (id: string) => void }) { return <nav aria-label="手册章节" className="space-y-1"><p className="mb-2 px-3 text-[11px] font-bold uppercase tracking-wider text-gold">开始使用</p>{chapters.filter(item => item.category === 'quickstart').map(item => <ChapterButton key={item.id} chapter={item} active={active === item.id} onSelect={onSelect} />)}<p className="mb-2 mt-6 px-3 text-[11px] font-bold uppercase tracking-wider text-gold">功能参考</p>{chapters.filter(item => item.category === 'reference').map(item => <ChapterButton key={item.id} chapter={item} active={active === item.id} onSelect={onSelect} />)}</nav>; }

/** 渲染章节入口，并把选择结果交给上层导航。 */
function ChapterButton({ chapter, active, onSelect }: { chapter: ManualChapter; active: boolean; onSelect: (id: string) => void }) { return <button type="button" onClick={() => onSelect(chapter.id)} className={`block w-full rounded px-3 py-2.5 text-left text-sm ${active ? 'bg-accent-light font-semibold text-accent' : 'text-muted hover:bg-accent-light'}`}>{chapter.title}</button>; }

function ChapterContent({ chapter, onOpen, onPlay, onOpenStep }: { chapter: ManualChapter; onOpen: () => void; onPlay: () => void; onOpenStep: (stepId: string) => void }) {
  const tourSteps = chapter.tourStepId ? tourStepsForRoute(chapter.route, chapter.tourStepId) : [];
  const stepIndex = new Map(tourSteps.map((step, index) => [step.id, index + 1]));
  return <article className="max-w-3xl">
    <p className="text-[11px] font-bold uppercase tracking-[.15em] text-gold">{chapter.category === "quickstart" ? "快速开始" : "功能参考"}</p>
    <h2 className="mt-2 font-display text-3xl font-semibold">{chapter.title}</h2>
    <p className="mt-3 text-sm leading-7 text-muted">{chapter.summary}</p>
    {tourSteps.length > 1 && <div className="mt-5 rounded border border-accent/30 bg-accent-light px-4 py-3">
      <p className="text-sm font-semibold text-fg">本章页面引导共 {tourSteps.length} 步</p>
      <p className="mt-1 text-xs leading-5 text-muted">点击“播放本页引导”后，页面会按顺序高亮每个字段或按钮；数据由你自己填写，引导不会替你提交任何操作。</p>
    </div>}
    <div className="mt-6 space-y-4">{chapter.sections.map(item => {
      const number = item.tourStepId ? stepIndex.get(item.tourStepId) : undefined;
      return <section key={item.title} className="rounded border border-border bg-white p-5">
        <div className="flex items-start justify-between gap-3"><h3 className="font-display text-lg font-semibold">{item.title}</h3>{number && <span className="shrink-0 rounded-full bg-accent-light px-2 py-1 text-[11px] font-semibold text-accent">第 {number}/{tourSteps.length} 步</span>}</div>
        {item.paragraphs.map(paragraph => <p key={paragraph} className="mt-2 text-sm leading-7 text-muted">{paragraph}</p>)}
        {item.tourStepId && <button type="button" onClick={() => onOpenStep(item.tourStepId!)} className="mt-3 text-xs font-semibold text-accent underline underline-offset-2">从这一步开始播放后续引导</button>}
      </section>;
    })}</div>
    <div className="mt-6 flex flex-wrap gap-3"><button type="button" onClick={onOpen} className="inline-flex items-center gap-2 rounded border border-border bg-white px-4 py-2.5 text-sm font-semibold"><ExternalLink className="h-4 w-4" />打开功能</button><button type="button" onClick={onPlay} className="inline-flex items-center gap-2 rounded bg-accent px-4 py-2.5 text-sm font-semibold text-white"><BookOpen className="h-4 w-4" />播放本页引导</button></div>
  </article>;
}
