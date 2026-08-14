export type GuideCompletionAction = 'close' | 'skip' | 'finish' | 'escape';

export interface ContextTourStep {
  id: string;
  title: string;
  description: string;
  target: string;
  route: string;
}

const salesSteps: readonly ContextTourStep[] = [
  { id: 'sales-orders', title: '创建销售单', description: '先录入客户、商品和价格，保存为草稿。', target: '[data-guide="sales-orders"]', route: '/sales' },
  { id: 'sales-fulfillment', title: '出库与收款', description: '确认后按真实发生顺序登记出库和人民币收款。', target: '[data-guide="sales-fulfillment"]', route: '/sales' },
  { id: 'accounting-reconciliation', title: '账户对账', description: '用实际余额核对系统账面，确认每一笔差异。', target: '[data-guide="accounting-reconciliation"]', route: '/accounting' },
  { id: 'accounting-profit', title: '查看月利润', description: '月度利润汇总收入、批次成本与费用。', target: '[data-guide="accounting-profit"]', route: '/accounting' },
];

const accountingSteps: readonly ContextTourStep[] = salesSteps.filter(step => step.id.startsWith('accounting-'));
const salesPageSteps: readonly ContextTourStep[] = salesSteps.filter(step => step.id.startsWith('sales-'));

export const CONTEXT_TOUR_GROUPS: Readonly<Record<string, readonly ContextTourStep[]>> = {
  sales: salesPageSteps,
  accounting: accountingSteps,
  overview: [{ id: 'overview', title: '业务总览', description: '从品牌目录进入库存、销售和账务工作台。', target: '[data-guide="overview"]', route: '/' }],
  inventory: [{ id: 'inventory-summary', title: '库存概览', description: '这里汇总品牌、款式、数量和成本，帮助你快速掌握现货。', target: '[data-guide="inventory-summary"]', route: '/inventory' }],
  privnote: [{ id: 'privnote-create', title: '创建客户链接', description: '在这里选择报价、收款或消息类型，再生成一次性链接。', target: '[data-guide="privnote-create"]', route: '/privnote' }],
  prices: [{ id: 'prices-dashboard', title: '价格追踪', description: '查看来源报价、品牌筛选和最近价格变化。', target: '[data-guide="prices-dashboard"]', route: '/prices' }],
};

export const CONTEXT_TOUR_STEPS: readonly ContextTourStep[] = Object.values(CONTEXT_TOUR_GROUPS).flat();
export const GUIDE_TARGETS = Object.fromEntries(CONTEXT_TOUR_STEPS.map(step => [step.id, step.target])) as Record<string, string>;

export function completionForAction(action: GuideCompletionAction): { complete: boolean; open: boolean } {
  return { complete: true, open: false };
}

export type GuideActionScope = 'welcome' | 'context';

export function guideActionPlan(_action: GuideCompletionAction, scope: GuideActionScope): { requiresPersistence: boolean; close: boolean } {
  return { requiresPersistence: scope === 'welcome', close: true };
}

export function createGuideActionRunner(complete: () => Promise<unknown>) {
  let busy = false;
  return {
    isBusy: () => busy,
    run: async (_action: GuideCompletionAction, onError?: (error: Error) => void): Promise<boolean> => {
      if (busy) return false;
      busy = true;
      try { await complete(); return true; }
      catch (error) { onError?.(error instanceof Error ? error : new Error('引导状态保存失败')); return false; }
      finally { busy = false; }
    },
  };
}

export function missingTargetAction(): { complete: false; open: false; error: string } {
  return { complete: false, open: false, error: '当前页面暂时无法播放本页引导，请刷新后重试。' };
}

export function tourStepsForRoute(route: string, id?: string): readonly ContextTourStep[] {
  const pathname = route.split('#', 1)[0];
  const group = pathname === '/' ? 'overview' : pathname === '/sales' ? 'sales' : pathname === '/accounting' ? 'accounting' : pathname === '/inventory' ? 'inventory' : pathname === '/privnote' ? 'privnote' : pathname === '/prices' ? 'prices' : '';
  const available = CONTEXT_TOUR_GROUPS[group] || [];
  const steps = available;
  if (!id) return steps;
  const requestedIndex = steps.findIndex(step => step.id === id);
  if (requestedIndex < 0) return [];
  return steps.slice(requestedIndex);
}

export function resolveTourTarget(id: string, availableSelectors: readonly string[]): string | null {
  const step = CONTEXT_TOUR_STEPS.find(item => item.id === id);
  if (!step || !availableSelectors.includes(step.target)) return null;
  return step.target;
}

export function isGuideExcludedRoute(pathname: string): boolean {
  return pathname === '/login' || pathname.startsWith('/p/');
}
