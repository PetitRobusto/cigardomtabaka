// 动作卡只维护自己的输入和结果，避免局部失败覆盖统计或其他动作。
export type ActionCard = 'exchange' | 'purchase' | 'expense' | 'dividend';

export type ActionStatus = 'idle' | 'loading' | 'success' | 'error' | 'conflict';

export interface ActionError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ActionState {
  status: ActionStatus;
  input: Record<string, unknown>;
  result?: unknown;
  error?: ActionError;
}

export type ActionStateAction =
  | { type: 'loading' }
  | { type: 'success'; result: unknown }
  | { type: 'error'; code: string; message: string; details?: Record<string, unknown> }
  | { type: 'conflict'; code: string; message: string; details?: Record<string, unknown> };

export function initialActionState(input: Record<string, unknown> = {}): ActionState {
  return { status: 'idle', input: { ...input } };
}

export function reduceActionState(state: ActionState, action: ActionStateAction): ActionState {
  switch (action.type) {
    case 'loading':
      return { ...state, status: 'loading', error: undefined };
    case 'success':
      return { ...state, status: 'success', result: action.result, error: undefined };
    case 'error':
      return {
        ...state,
        status: 'error',
        error: { code: action.code, message: action.message, details: action.details },
      };
    case 'conflict':
      return {
        ...state,
        status: 'conflict',
        error: { code: action.code, message: action.message, details: action.details },
      };
    default:
      return state;
  }
}
