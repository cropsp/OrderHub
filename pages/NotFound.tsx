
import React from 'react';
import { Link } from 'react-router-dom';

const NotFound: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center">
        <h1 className="text-6xl font-bold text-primary">404</h1>
        <h2 className="text-3xl font-semibold mt-4">Page Not Found</h2>
        <p className="mt-2 text-text-secondary">Sorry, the page you are looking for does not exist.</p>
        <Link to="/" className="mt-6 px-4 py-2 bg-primary text-white rounded-md hover:bg-indigo-500">
            Go to Dashboard
        </Link>
    </div>
  );
};

export default NotFound;
