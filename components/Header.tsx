
import React from 'react';

interface HeaderProps {
  title: string;
}

const Header: React.FC<HeaderProps> = ({ title }) => {
  return (
    <h1 className="text-3xl font-semibold text-text-primary mb-6">{title}</h1>
  );
};

export default Header;
