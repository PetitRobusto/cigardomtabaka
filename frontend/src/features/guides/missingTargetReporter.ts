export interface MissingTargetReporter {
  report(): void;
  cancel(): void;
}

export function createMissingTargetReporter(
  onMissingTarget: () => void,
  delay = 1200,
  schedule: typeof setTimeout = setTimeout,
  cancelSchedule: typeof clearTimeout = clearTimeout,
): MissingTargetReporter {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let reported = false;
  return {
    report() {
      if (reported || timer !== null) return;
      timer = schedule(() => {
        timer = null;
        if (!reported) {
          reported = true;
          onMissingTarget();
        }
      }, delay);
    },
    cancel() {
      if (timer !== null) cancelSchedule(timer);
      timer = null;
    },
  };
}
