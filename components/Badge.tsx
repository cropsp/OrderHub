
import React from 'react';
import { OrderSource, OrderStatus } from '../types';

interface BadgeProps {
  type: OrderSource | OrderStatus;
}

const Badge: React.FC<BadgeProps> = ({ type }) => {
  const baseClasses = 'px-2 py-1 text-xs font-semibold leading-tight rounded-full';
  
  const typeStyles: Record<string, string> = {
    // Sources
    [OrderSource.Shopify]: 'bg-blue-200 text-blue-800',
    [OrderSource.Etsy]: 'bg-orange-200 text-orange-800',
    [OrderSource.Manual]: 'bg-gray-200 text-gray-800',
    // Statuses
    [OrderStatus.New]: 'bg-green-200 text-green-800',
    [OrderStatus.InProgress]: 'bg-yellow-200 text-yellow-800',
    [OrderStatus.Manufactured]: 'bg-purple-200 text-purple-800',
    [OrderStatus.Shipped]: 'bg-gray-500 text-gray-100',
  };

  const className = `${baseClasses} ${typeStyles[type] || 'bg-gray-200 text-gray-800'}`;

  return (
    <span className={className}>
      {type}
    </span>
  );
};

export default Badge;
