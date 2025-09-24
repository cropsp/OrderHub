
import React from 'react';
import Header from '../components/Header';

const Settings: React.FC = () => {
  return (
    <>
      <Header title="Settings" />
      <div className="bg-card p-6 rounded-lg shadow-md">
        <p>This is the settings page. Configuration options will be available here in a future update.</p>
      </div>
    </>
  );
};

export default Settings;
