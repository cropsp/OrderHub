
import React, { useState } from 'react';
import Header from '../components/Header';

type Tab = 'Shopify' | 'Etsy';

const IntegrationConfig: React.FC<{ platform: Tab }> = ({ platform }) => (
    <div className="bg-card p-6 rounded-lg shadow-md">
        <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold">{platform} Integration</h2>
            <span className="text-sm font-medium text-green-400">Status: Connected</span>
        </div>
        <form>
            <div className="space-y-4">
                <div>
                    <label className="block text-sm font-medium mb-1">API Key</label>
                    <input type="password" value="••••••••••••••••" readOnly className="w-full px-3 py-2 bg-gray-700 border border-border rounded-md" />
                </div>
                <div>
                    <label className="block text-sm font-medium mb-1">API Secret</label>
                    <input type="password" value="••••••••••••••••" readOnly className="w-full px-3 py-2 bg-gray-700 border border-border rounded-md" />
                </div>
            </div>
            <div className="mt-6 flex justify-end">
                <button type="button" onClick={() => alert(`${platform} resync started!`)} className="px-4 py-2 bg-secondary text-white rounded-md hover:bg-emerald-500">Resync</button>
            </div>
        </form>
    </div>
);


const Integrations: React.FC = () => {
    const [activeTab, setActiveTab] = useState<Tab>('Shopify');

    const tabClasses = (tabName: Tab) => `py-2 px-4 cursor-pointer rounded-t-lg ${activeTab === tabName ? 'bg-card text-white' : 'text-gray-400 hover:bg-gray-700'}`;

    return (
        <>
            <Header title="Integrations" />
            
            <div className="w-full">
                <div className="flex border-b border-border">
                    <div className={tabClasses('Shopify')} onClick={() => setActiveTab('Shopify')}>Shopify</div>
                    <div className={tabClasses('Etsy')} onClick={() => setActiveTab('Etsy')}>Etsy</div>
                </div>

                <div className="mt-4">
                    {activeTab === 'Shopify' && <IntegrationConfig platform="Shopify" />}
                    {activeTab === 'Etsy' && <IntegrationConfig platform="Etsy" />}
                </div>
            </div>
        </>
    );
};

export default Integrations;
