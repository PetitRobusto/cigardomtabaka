export type Day1StatusState = { status: 'loading' | 'ready' | 'error'; day1Status?: string; message?: string };

export const DAY1_STATUS_ERROR_MESSAGE = '暂时无法确认初始化状态，将返回账务工作台。';

export function day1StatusLoadingState(): Day1StatusState { return { status: 'loading' }; }
export function day1StatusReadyState(day1Status: string): Day1StatusState { return { status: 'ready', day1Status }; }
export function day1StatusErrorState(): Day1StatusState { return { status: 'error', message: DAY1_STATUS_ERROR_MESSAGE }; }
export function day1StatusNavigation(state: Day1StatusState): '/accounting' | '/accounting/day1' {
  return state.status === 'ready' && state.day1Status === 'completed' ? '/accounting/day1' : '/accounting';
}
