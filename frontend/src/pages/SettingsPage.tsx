import { useEffect, useState } from 'react';
import { Mail, Shield, UserCircle2, LogOut } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useAuth } from '@/hooks/useAuth';

import ShellPage from './ShellPage';

const SETTINGS_STORAGE_KEY = 'orderhub.settings';

type SystemPreferences = {
  dashboard_refresh_seconds: '60' | '300';
  order_view_default: 'table' | 'board';
  date_display: 'local' | 'utc';
  default_timezone: string;
};

const DEFAULT_PREFERENCES: SystemPreferences = {
  dashboard_refresh_seconds: '60',
  order_view_default: 'table',
  date_display: 'local',
  default_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
};

function roleLabel(role: string) {
  return role.charAt(0).toUpperCase() + role.slice(1);
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [preferences, setPreferences] = useState<SystemPreferences>(DEFAULT_PREFERENCES);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return;

    try {
      const parsed = JSON.parse(raw) as Partial<SystemPreferences>;
      setPreferences({
        dashboard_refresh_seconds:
          parsed.dashboard_refresh_seconds === '300' ? '300' : '60',
        order_view_default: parsed.order_view_default === 'board' ? 'board' : 'table',
        date_display: parsed.date_display === 'utc' ? 'utc' : 'local',
        default_timezone: parsed.default_timezone || DEFAULT_PREFERENCES.default_timezone,
      });
    } catch {
      setPreferences(DEFAULT_PREFERENCES);
    }
  }, []);

  const savePreferences = () => {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(preferences));
    setSaveMessage('Preferences saved locally.');
    window.setTimeout(() => setSaveMessage(null), 2000);
  };

  const onLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
    } finally {
      setIsLoggingOut(false);
    }
  };

  return (
    <ShellPage
      title="Settings"
      description="Account profile and access settings."
    >
      <div className="mx-auto grid w-full max-w-3xl gap-6">
        <Card className="border-slate-800/60 bg-slate-900/40 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-slate-100">Profile</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="flex items-center gap-3 text-slate-200">
              <UserCircle2 className="h-5 w-5 text-slate-400" />
              <span>{user?.full_name ?? 'Unknown user'}</span>
            </div>

            <div className="flex items-center gap-3 text-slate-300">
              <Mail className="h-5 w-5 text-slate-500" />
              <span>{user?.email ?? 'No email'}</span>
            </div>

            <div className="flex items-center gap-3">
              <Shield className="h-5 w-5 text-slate-500" />
              <Badge variant="outline" className="border-slate-700 bg-slate-800/40 text-slate-200">
                {roleLabel(user?.role ?? 'unknown')}
              </Badge>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-800/60 bg-slate-900/40 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-slate-100">System Preferences</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Dashboard Refresh Interval
              </p>
              <Select
                value={preferences.dashboard_refresh_seconds}
                onValueChange={(value) =>
                  setPreferences((prev) => ({
                    ...prev,
                    dashboard_refresh_seconds: value as SystemPreferences['dashboard_refresh_seconds'],
                  }))
                }
              >
                <SelectTrigger className="w-full border-slate-700 bg-slate-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-slate-800 bg-slate-900">
                  <SelectItem value="60">Every 1 minute</SelectItem>
                  <SelectItem value="300">Every 5 minutes</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Default Orders View
              </p>
              <Select
                value={preferences.order_view_default}
                onValueChange={(value) =>
                  setPreferences((prev) => ({
                    ...prev,
                    order_view_default: value as SystemPreferences['order_view_default'],
                  }))
                }
              >
                <SelectTrigger className="w-full border-slate-700 bg-slate-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-slate-800 bg-slate-900">
                  <SelectItem value="table">Table</SelectItem>
                  <SelectItem value="board">Pipeline Board</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Date Display</p>
              <Select
                value={preferences.date_display}
                onValueChange={(value) =>
                  setPreferences((prev) => ({
                    ...prev,
                    date_display: value as SystemPreferences['date_display'],
                  }))
                }
              >
                <SelectTrigger className="w-full border-slate-700 bg-slate-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-slate-800 bg-slate-900">
                  <SelectItem value="local">Local Time</SelectItem>
                  <SelectItem value="utc">UTC</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Preferred Timezone</p>
              <Input
                className="border-slate-700 bg-slate-900/50"
                placeholder="Etc/UTC"
                value={preferences.default_timezone}
                onChange={(event) =>
                  setPreferences((prev) => ({
                    ...prev,
                    default_timezone: event.target.value,
                  }))
                }
              />
            </div>

            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-500">
                These preferences are stored in your browser for this device.
              </p>
              <Button className="bg-teal-600 text-white hover:bg-teal-500" onClick={savePreferences}>
                Save Preferences
              </Button>
            </div>

            {saveMessage && (
              <p className="text-xs text-teal-300">{saveMessage}</p>
            )}
          </CardContent>
        </Card>

        <Card className="border-slate-800/60 bg-slate-900/40 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-slate-100">Session</CardTitle>
          </CardHeader>
          <CardContent>
            <Button
              className="bg-red-600 text-white hover:bg-red-500"
              disabled={isLoggingOut}
              onClick={onLogout}
            >
              <LogOut className="mr-2 h-4 w-4" />
              {isLoggingOut ? 'Signing out...' : 'Sign out'}
            </Button>
          </CardContent>
        </Card>
      </div>
    </ShellPage>
  );
}
