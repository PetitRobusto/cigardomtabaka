import { BrandLoader } from './BrandLoader';

export function LoadingState({ text = '加载中…' }: { text?: string }) {
  return <BrandLoader text={text} />;
}
