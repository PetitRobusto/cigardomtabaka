import { useContext, useEffect } from 'react';
import { UNSAFE_DataRouterContext, useBlocker } from 'react-router-dom';

export const discardDraftMessage = '商品修改尚未保存，确定放弃修改并离开吗？';

function RouteGuard({ dirty, busy }: { dirty: boolean; busy: boolean }) {
  const blocker = useBlocker(dirty || busy);
  useEffect(() => {
    if (blocker.state !== 'blocked') return;
    if (!busy && window.confirm(discardDraftMessage)) blocker.proceed();
    else blocker.reset();
  }, [blocker, busy]);
  return null;
}

export default function DraftNavigationGuard({ dirty, busy }: { dirty: boolean; busy: boolean }) {
  const router = useContext(UNSAFE_DataRouterContext);
  useEffect(() => {
    if (!dirty && !busy) return;
    const leave = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', leave);
    return () => window.removeEventListener('beforeunload', leave);
  }, [dirty, busy]);
  return router ? <RouteGuard dirty={dirty} busy={busy} /> : null;
}
