import { useLocation } from 'react-router-dom';
import { DelayedAppSkeleton } from '../layout/AppSkeleton';

export function LoadingState({ text = '加载中…' }: { text?: string }) {
  const location = useLocation();
  return <DelayedAppSkeleton path={location.pathname} label={text} />;
}
