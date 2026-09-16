// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import StoreHeader from './StoreHeader';

afterEach(cleanup);

describe('StoreHeader', () => {
  it('shows the Habanos Specialist mark and professional credential', () => {
    render(<StoreHeader />);

    expect(screen.getByRole('img', { name: 'Habanos Specialist' })).not.toBeNull();
    expect(screen.getByText(/Habanos Specialist · 专业门店资质/)).not.toBeNull();
    expect(screen.getByText('莫斯科持证雪茄服务商')).not.toBeNull();
  });

  it('keeps the compact payment header concise', () => {
    render(<StoreHeader compact />);

    expect(screen.getByRole('img', { name: 'Habanos Specialist' })).not.toBeNull();
    expect(screen.queryByText('莫斯科持证雪茄服务商')).toBeNull();
  });
});
