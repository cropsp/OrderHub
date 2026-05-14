import React from 'react';
import { render, screen } from '@testing-library/react';

import RevenueChart from '../RevenueChart';

describe('RevenueChart', () => {
  it('shows empty state when data is empty', () => {
    const { container } = render(<RevenueChart data={[]} />);
    expect(screen.getByText('No revenue data')).toBeInTheDocument();
    expect(container.querySelector('.recharts-wrapper')).toBeNull();
  });

  it('renders AreaChart when data is provided', () => {
    const data = [
      { date: '2026-05-01', revenue: 100 },
      { date: '2026-05-02', revenue: 150 },
    ];
    const { container } = render(<RevenueChart data={data} />);
    expect(screen.queryByText('No revenue data')).not.toBeInTheDocument();
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull();
  });
});
