
import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import useAuth from '../hooks/useAuth';
import { DashboardIcon } from './icons/DashboardIcon';
import { OrdersIcon } from './icons/OrdersIcon';
import { ProductsIcon } from './icons/ProductsIcon';
import { ReportsIcon } from './icons/ReportsIcon';
import { IntegrationsIcon } from './icons/IntegrationsIcon';
import { SettingsIcon } from './icons/SettingsIcon';
import { PlusIcon } from './icons/PlusIcon';


interface NavItemProps {
  to: string;
  icon: React.ReactNode;
  label: string;
}

const NavItem: React.FC<NavItemProps> = ({ to, icon, label }) => (
  <NavLink
    to={to}
    className={({ isActive }) =>
      `flex items-center px-4 py-2 mt-2 text-gray-400 transition-colors duration-300 transform rounded-lg hover:bg-gray-700 hover:text-gray-200 ${
        isActive ? 'bg-gray-700 text-gray-200' : ''
      }`
    }
  >
    {icon}
    <span className="mx-4 font-medium">{label}</span>
  </NavLink>
);

const Sidebar: React.FC = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex flex-col w-64 h-screen px-4 py-8 bg-sidebar border-r border-border">
      <h2 className="text-3xl font-semibold text-center text-text-primary">
        OrderHub
      </h2>

      <div className="flex flex-col justify-between flex-1 mt-6">
        <nav>
          <NavItem to="/" icon={<DashboardIcon />} label="Dashboard" />
          <NavItem to="/orders" icon={<OrdersIcon />} label="Orders" />
          <NavItem to="/products" icon={<ProductsIcon />} label="Products" />
          <NavItem to="/reports" icon={<ReportsIcon />} label="Reports" />
          <NavItem to="/integrations" icon={<IntegrationsIcon />} label="Integrations" />
          <NavItem to="/settings" icon={<SettingsIcon />} label="Settings" />
          <div className="px-4 py-2 mt-4">
             <button onClick={() => navigate('/new-order')} className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium tracking-wide text-white capitalize transition-colors duration-300 transform bg-primary rounded-lg hover:bg-indigo-500 focus:outline-none focus:ring focus:ring-indigo-300 focus:ring-opacity-80">
                <PlusIcon />
                <span className="mx-1">New Order</span>
            </button>
          </div>
        </nav>

        <div className="mt-auto">
          <button
            onClick={logout}
            className="w-full px-4 py-2 mt-2 text-left text-gray-400 transition-colors duration-300 transform rounded-lg hover:bg-gray-700 hover:text-gray-200"
          >
            Logout
          </button>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
