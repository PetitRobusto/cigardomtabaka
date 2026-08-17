import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { completeGuide, fetchGuideStatus } from '../../api';
import { useAuthStore } from '../../store/authStore';
import { canShowGuide } from './guideState';
import { createGuideActionRunner, guideActionPlan, isGuideExcludedRoute } from './guideInteractions';
import WelcomeGuide from './WelcomeGuide';
import ContextTour from './ContextTour';
import type { GuideActionScope, GuideCompletionAction } from './guideInteractions';

export default function GuideController() {
  const { user, isAuthenticated, isLoading } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [welcomeOpen, setWelcomeOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [statusError, setStatusError] = useState('');
  const [actionBusy, setActionBusy] = useState(false);
  const actionRunner = useRef(createGuideActionRunner(completeGuide)).current;

  const staff = Boolean(isAuthenticated && user?.is_staff);
  const excluded = isGuideExcludedRoute(location.pathname);
  const requestedTour = !excluded && staff ? (location.state as { guideTourId?: string } | null)?.guideTourId : undefined;

  useEffect(() => {
    if (isLoading || !staff || excluded) return;
    let active = true;
    const load = async () => {
      try {
        const summary = user?.guide || await fetchGuideStatus();
        if (active && canShowGuide(summary, { isAuthenticated, isStaff: true })) setWelcomeOpen(true);
      } catch (error) {
        if (active) setStatusError(error instanceof Error ? error.message : '引导状态加载失败');
      }
    };
    void load();
    return () => { active = false; };
  }, [excluded, isAuthenticated, isLoading, staff, user?.guide]);

  const clearTourState = useCallback(() => {
    if (requestedTour) navigate(location.pathname + location.search + location.hash, { replace: true, state: null });
  }, [location.hash, location.pathname, location.search, navigate, requestedTour]);

  const handleAction = useCallback(async (action: GuideCompletionAction, scope: GuideActionScope = 'welcome'): Promise<boolean> => {
    const plan = guideActionPlan(action, scope);
    if (!plan.requiresPersistence) {
      if (plan.close) clearTourState();
      return true;
    }
    if (actionRunner.isBusy()) return false;
    setActionBusy(true);
    const succeeded = await actionRunner.run(action, error => setStatusError(error.message));
    setActionBusy(false);
    if (succeeded) {
      setStatusError('');
      if (plan.close) setWelcomeOpen(false);
    }
    return succeeded;
  }, [actionRunner, clearTourState]);

  const onEscape = useCallback((event: KeyboardEvent) => {
    if (event.key !== 'Escape' || (!welcomeOpen && !requestedTour)) return;
    event.preventDefault();
    void handleAction('escape', welcomeOpen ? 'welcome' : 'context');
  }, [handleAction, requestedTour, welcomeOpen]);

  useEffect(() => {
    document.addEventListener('keydown', onEscape);
    return () => document.removeEventListener('keydown', onEscape);
  }, [onEscape]);

  const handleMissingTarget = useCallback(() => {
    setStatusError('当前页面暂时无法播放本页引导，请刷新后重试。');
    setWelcomeOpen(false);
    clearTourState();
  }, [clearTourState]);

  if (!staff || excluded) return null;
  return <>
    {statusError && <div role="status" className="fixed bottom-4 left-4 z-[100] flex max-w-sm items-start gap-3 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"><span>{statusError}，引导已关闭，可稍后从帮助中心重新播放。</span><button type="button" aria-label="关闭引导错误" onClick={() => setStatusError('')} className="shrink-0 text-lg leading-none">×</button></div>}
    {welcomeOpen && <WelcomeGuide busy={actionBusy} stepIndex={stepIndex} onPrevious={() => setStepIndex(value => Math.max(0, value - 1))} onNext={() => setStepIndex(value => value + 1)} onAction={async action => { const succeeded = await handleAction(action); if (succeeded && action === 'finish') navigate('/sales', { state: { guideTourId: 'sales-orders' } }); }} />}
    {!welcomeOpen && requestedTour && <><style>{'.guide-target-highlight{position:relative;z-index:70;outline:3px solid #7A1F2E;outline-offset:5px;box-shadow:0 0 0 9999px rgba(44,36,22,.36),0 8px 28px rgba(122,31,46,.25);border-radius:8px;}'}</style><ContextTour busy={actionBusy} stepId={requestedTour} onAction={action => { void handleAction(action, 'context'); }} onMissingTarget={handleMissingTarget} /></>}
  </>;
}
