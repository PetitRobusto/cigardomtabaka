import type { Day1State } from '../../types';
import type { Day1Payload } from '../../features/day1/day1State';
import {
  buildDay1Payload,
  normalizeDay1Draft,
  type Day1DraftInput,
} from './day1State';

type SaveDay1 = (payload: Day1Payload, expectedVersion: number) => Promise<Day1State>;
type ConfirmDay1 = (version: number, idempotencyKey: string) => Promise<Day1State>;

export function saveThenConfirmDay1({
  draft,
  baseVersion,
  idempotencyKey,
  save,
  confirm,
  onSaved,
}: {
  draft: Day1DraftInput;
  baseVersion: number;
  idempotencyKey: string;
  save: SaveDay1;
  confirm: ConfirmDay1;
  onSaved?: (saved: Day1State) => void;
}): Promise<{ saved: Day1State; confirmed: Day1State }> {
  return save(buildDay1Payload(draft), baseVersion).then(saved => {
    onSaved?.(saved);
    return confirm(saved.version, idempotencyKey).then(confirmed => ({ saved, confirmed }));
  });
}

export function refreshDay1State({
  localDraft,
  baseVersion,
  incoming,
  mode,
}: {
  localDraft: Day1DraftInput;
  baseVersion: number;
  incoming: Day1State;
  mode: 'preserve-local' | 'discard-local';
}): { server: Day1State; draft: Day1DraftInput; baseVersion: number } {
  if (mode === 'preserve-local') return { server: incoming, draft: localDraft, baseVersion };
  return {
    server: incoming,
    draft: normalizeDay1Draft(incoming, incoming.business_date || localDraft.business_date),
    baseVersion: incoming.version,
  };
}

export function day1WriteGate(status: string, acknowledged: boolean): boolean {
  return status !== 'completed' && acknowledged;
}
