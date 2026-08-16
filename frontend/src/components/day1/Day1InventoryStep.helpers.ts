import { fetchCigarDetail } from '../../api';
import type { CigarDetailResponse } from '../../types';
import { declaredBoxSizes } from '../../features/day1/day1State';

export function boxSizesFromCigarDetail(detail: Pick<CigarDetailResponse, 'cigar'> | { cigar: { box_sizes: unknown[] } }): number[] {
  return declaredBoxSizes(detail.cigar.box_sizes);
}

export function fetchDeclaredBoxSizes(cigarId: number): Promise<number[]> {
  return fetchCigarDetail(cigarId).then(boxSizesFromCigarDetail);
}

export function applyIfDay1InventoryMounted(mounted: boolean, update: () => void): boolean {
  // 详情请求晚于页面离开时，不再更新已卸载表单。
  if (!mounted) return false;
  update();
  return true;
}

export function createDay1InventoryMountGuard() {
  let mounted = false;
  return {
    setup() {
      // StrictMode 会重放 setup/cleanup，setup 必须恢复实时状态。
      mounted = true;
      return () => { mounted = false; };
    },
    run(update: () => void): boolean {
      return applyIfDay1InventoryMounted(mounted, update);
    },
    isMounted() {
      return mounted;
    },
  };
}

interface Day1InventoryAddFlow {
  loadBoxSizes: () => Promise<number[]>;
  isMounted: () => boolean;
  run: (update: () => void) => boolean;
  onSuccess: (boxSizes: number[]) => void;
  onError: () => void;
  onFinally: () => void;
}

export function runDay1InventoryAdd({ loadBoxSizes, isMounted, run, onSuccess, onError, onFinally }: Day1InventoryAddFlow): Promise<void> {
  return loadBoxSizes().then(boxSizes => {
    // 卸载后的详情响应在调用表单回调前丢弃。
    if (isMounted()) run(() => onSuccess(boxSizes));
  }).catch(() => {
    run(onError);
  }).finally(() => {
    run(onFinally);
  });
}

export function resolveDay1BoxState(hasCatalogOverride: boolean, state: 'loading' | 'loaded' | 'error' | undefined): 'loading' | 'loaded' | 'error' {
  // 未知状态表示详情仍在请求，手动包装规格继续锁定。
  return hasCatalogOverride ? 'loaded' : (state || 'loading');
}

export function createBoxSizesLoader(fetchSizes: (cigarId: number) => Promise<number[]>): (cigarId: number) => Promise<number[]> {
  const inFlight = new Map<number, Promise<number[]>>();
  return (cigarId: number) => {
    const existing = inFlight.get(cigarId);
    if (existing) return existing;
    // 并发调用共享一个请求，失败后清除以便下次重试。
    const request = fetchSizes(cigarId).catch(error => {
      inFlight.delete(cigarId);
      throw error;
    });
    inFlight.set(cigarId, request);
    return request;
  };
}
