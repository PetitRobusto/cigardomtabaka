// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import StoreHeader from './StoreHeader';

afterEach(cleanup);

describe('StoreHeader', () => {
  it('shows the store without claiming Habanos Specialist status', () => {
    render(<StoreHeader />);

    expect(screen.queryByRole('img', { name: 'Habanos Specialist' })).toBeNull();
    expect(screen.queryByText(/专业门店资质/)).toBeNull();
    expect(screen.getByText('莫斯科雪茄门店')).not.toBeNull();
  });

  it('keeps the compact payment header concise', () => {
    render(<StoreHeader compact />);

    expect(screen.queryByRole('img', { name: 'Habanos Specialist' })).toBeNull();
    expect(screen.queryByText('莫斯科雪茄门店')).toBeNull();
  });
});
