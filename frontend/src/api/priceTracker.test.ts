import { beforeEach, describe, expect, it, vi } from 'vitest';

const client = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    create: () => client,
    isAxiosError: (value: unknown) => Boolean((value as { isAxiosError?: boolean })?.isAxiosError),
  },
}));

import { fetchAggregatedPrices } from '../api';

function response<T>(data: T) {
  return Promise.resolve({ data });
}

describe('price tracker API contracts', () => {
  beforeEach(() => vi.clearAllMocks());

  it('uses the backend list action for aggregated dashboard prices', async () => {
    const data = [{ cigar_id: 1, sources: [] }];
    client.get.mockReturnValueOnce(response(data));

    await expect(fetchAggregatedPrices()).resolves.toEqual(data);
    expect(client.get).toHaveBeenCalledWith('/prices/snapshots/list/', { params: {} });
  });

  it('returns a safe empty list for a malformed aggregate response', async () => {
    client.get.mockReturnValueOnce(response({ unexpected: true }));

    await expect(fetchAggregatedPrices()).resolves.toEqual([]);
  });
});
