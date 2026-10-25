// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import StoreHeader from './StoreHeader';

afterEach(cleanup);

describe('StoreHeader', () => {
  it('shows the store brand without specialist credentials', () => {
    render(<StoreHeader />);

    expect(screen.queryByRole('img', { name: 'Habanos Specialist' })).toBeNull();
    expect(screen.getByRole('img', { name: 'CigarDomTabaka' })).not.toBeNull();
    expect(screen.queryByText(/Habanos Specialist|专业门店资质/)).toBeNull();
    expect(screen.queryByText('莫斯科持证雪茄服务商')).toBeNull();
  });

  it('keeps the compact payment header concise', () => {
    render(<StoreHeader compact />);

    expect(screen.queryByRole('img', { name: 'Habanos Specialist' })).toBeNull();
    expect(screen.getByRole('img', { name: 'CigarDomTabaka' })).not.toBeNull();
    expect(screen.queryByText('莫斯科持证雪茄服务商')).toBeNull();
  });
});
