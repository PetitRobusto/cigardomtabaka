/** Web Locks substitute for jsdom; serialize each named critical section. */
export function installIncomeTestLocks() {
  const tails = new Map<string, Promise<unknown>>();
  Object.defineProperty(navigator, 'locks', { configurable: true, value: {
    request: <T>(name: string, callback: () => T) => {
      const result = (tails.get(name) || Promise.resolve()).then(callback);
      tails.set(name, result.catch(() => undefined));
      return result;
    },
  } });
}
