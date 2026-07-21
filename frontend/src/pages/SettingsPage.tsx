import { useState } from 'react';
import { Mail, MapPinCheck, Shield, Truck, UserCircle2, LogOut } from 'lucide-react';

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
import {
  useAddressValidationKey,
  useSetAddressValidationKey,
  useWesternBidCredentials,
  useSetWesternBidCredentials,
} from '@/hooks/useAppSettings';
import { useAuth } from '@/hooks/useAuth';
import { useUpdatePreferences } from '@/hooks/useUsers';

import ShellPage from './ShellPage';


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

function normalizePreferences(raw: unknown): SystemPreferences {
  const saved = (raw ?? {}) as Partial<SystemPreferences>;
  return {
    dashboard_refresh_seconds:
      saved.dashboard_refresh_seconds === '300' ? '300' : '60',
    order_view_default: saved.order_view_default === 'board' ? 'board' : 'table',
    date_display: saved.date_display === 'utc' ? 'utc' : 'local',
    default_timezone: saved.default_timezone || DEFAULT_PREFERENCES.default_timezone,
  };
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const updatePreferences = useUpdatePreferences();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [preferences, setPreferences] = useState<SystemPreferences>(() => normalizePreferences(user?.preferences));
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  // The address-validation key is a global app setting, so its endpoints are
  // owner-only — but /settings itself is open to every role. Gate both the query
  // and the card, or non-owners would just see a section that 403s.
  const isOwner = user?.role === 'owner';
  const addressKey = useAddressValidationKey({ enabled: isOwner });
  const setAddressKey = useSetAddressValidationKey();
  const [googleApiKey, setGoogleApiKey] = useState('');
  const [keyMessage, setKeyMessage] = useState<string | null>(null);

  const saveGoogleApiKey = async () => {
    const trimmed = googleApiKey.trim();
    if (!trimmed) return;
    try {
      await setAddressKey.mutateAsync(trimmed);
      setGoogleApiKey('');
      setKeyMessage('API key saved.');
      window.setTimeout(() => setKeyMessage(null), 2000);
    } catch {
      setKeyMessage('Failed to save the API key.');
    }
  };

  // WesternBid credentials — owner-only, same masking discipline as the Google
  // key. Both the API key and login are secrets, so both are write-only.
  const wbCreds = useWesternBidCredentials({ enabled: isOwner });
  const setWbCreds = useSetWesternBidCredentials();
  const [wbApiKey, setWbApiKey] = useState('');
  const [wbLogin, setWbLogin] = useState('');
  const [wbMessage, setWbMessage] = useState<string | null>(null);

  const saveWbCredentials = async () => {
    const apiKey = wbApiKey.trim();
    const login = wbLogin.trim();
    if (!apiKey || !login) return;
    try {
      await setWbCreds.mutateAsync({ api_key: apiKey, login });
      setWbApiKey('');
      setWbLogin('');
      setWbMessage('WesternBid credentials saved.');
      window.setTimeout(() => setWbMessage(null), 2000);
    } catch {
      setWbMessage('Failed to save WesternBid credentials.');
    }
  };

  // Sync preferences when the user object changes (e.g. after login/refresh).
  // Derive state during render rather than in an effect to avoid cascading re-renders.
  const [syncedPrefs, setSyncedPrefs] = useState(user?.preferences);
  if (syncedPrefs !== user?.preferences) {
    setSyncedPrefs(user?.preferences);
    setPreferences(normalizePreferences(user?.preferences));
  }

  const savePreferences = async () => {
    try {
      await updatePreferences.mutateAsync(preferences);
      setSaveMessage('Preferences saved to server.');
      window.setTimeout(() => setSaveMessage(null), 2000);
    } catch {
      setSaveMessage('Failed to save preferences.');
    }
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
        <Card className="border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-zinc-100">Profile</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="flex items-center gap-3 text-zinc-200">
              <UserCircle2 className="h-5 w-5 text-zinc-400" />
              <span>{user?.full_name ?? 'Unknown user'}</span>
            </div>

            <div className="flex items-center gap-3 text-zinc-300">
              <Mail className="h-5 w-5 text-zinc-400" />
              <span>{user?.email ?? 'No email'}</span>
            </div>

            <div className="flex items-center gap-3">
              <Shield className="h-5 w-5 text-zinc-400" />
              <Badge variant="outline" className="border-zinc-700 bg-zinc-800/40 text-zinc-200">
                {roleLabel(user?.role ?? 'unknown')}
              </Badge>
            </div>
          </CardContent>
        </Card>

        <Card className="border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-zinc-100">System Preferences</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">
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
                <SelectTrigger className="w-full border-zinc-700 bg-zinc-900/50 text-zinc-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-800 bg-zinc-900">
                  <SelectItem value="60">Every 1 minute</SelectItem>
                  <SelectItem value="300">Every 5 minutes</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">
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
                <SelectTrigger className="w-full border-zinc-700 bg-zinc-900/50 text-zinc-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-800 bg-zinc-900">
                  <SelectItem value="table">Table</SelectItem>
                  <SelectItem value="board">Pipeline Board</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">Date Display</p>
              <Select
                value={preferences.date_display}
                onValueChange={(value) =>
                  setPreferences((prev) => ({
                    ...prev,
                    date_display: value as SystemPreferences['date_display'],
                  }))
                }
              >
                <SelectTrigger className="w-full border-zinc-700 bg-zinc-900/50 text-zinc-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-800 bg-zinc-900">
                  <SelectItem value="local">Local Time</SelectItem>
                  <SelectItem value="utc">UTC</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">Preferred Timezone</p>
              <Input
                className="border-zinc-700 bg-zinc-900/50"
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
              <p className="text-xs text-zinc-400">
                These preferences are synced across all your devices.
              </p>
              <Button 
                className="bg-teal-600 text-white hover:bg-teal-500" 
                onClick={savePreferences}
                disabled={updatePreferences.isPending}
              >
                {updatePreferences.isPending ? 'Saving...' : 'Save Preferences'}
              </Button>
            </div>

            {saveMessage && (
              <p className="text-xs text-teal-300">{saveMessage}</p>
            )}
          </CardContent>
        </Card>

        {isOwner && (
          <Card className="border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="text-zinc-100">Address Validation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center gap-3">
                <MapPinCheck className="h-5 w-5 text-zinc-400" />
                {addressKey.data?.is_set ? (
                  <Badge variant="outline" className="border-teal-800 bg-teal-950/40 text-teal-300">
                    Configured ••••{addressKey.data.last4}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="border-zinc-700 bg-zinc-800/40 text-zinc-400">
                    Not configured
                  </Badge>
                )}
              </div>

              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">
                  Google API Key
                </p>
                <Input
                  className="border-zinc-700 bg-zinc-900/50"
                  type="password"
                  autoComplete="off"
                  placeholder={
                    addressKey.data?.is_set ? 'Leave empty to keep existing' : 'Google API key'
                  }
                  value={googleApiKey}
                  onChange={(event) => setGoogleApiKey(event.target.value)}
                />
              </div>

              <div className="flex items-center justify-between">
                <p className="text-xs text-zinc-400">
                  Used to check non-Ukrainian shipping addresses. Stored encrypted; never shown again.
                </p>
                <Button
                  className="bg-teal-600 text-white hover:bg-teal-500"
                  onClick={saveGoogleApiKey}
                  disabled={setAddressKey.isPending || !googleApiKey.trim()}
                >
                  {setAddressKey.isPending ? 'Saving...' : 'Save Key'}
                </Button>
              </div>

              {keyMessage && <p className="text-xs text-teal-300">{keyMessage}</p>}
            </CardContent>
          </Card>
        )}

        {isOwner && (
          <Card className="border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="text-zinc-100">WesternBid</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center gap-3">
                <Truck className="h-5 w-5 text-zinc-400" />
                {wbCreds.data?.api_key_is_set && wbCreds.data?.login_is_set ? (
                  <Badge variant="outline" className="border-teal-800 bg-teal-950/40 text-teal-300">
                    Configured ••••{wbCreds.data.api_key_last4}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="border-zinc-700 bg-zinc-800/40 text-zinc-400">
                    Not configured
                  </Badge>
                )}
              </div>

              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">
                  WesternBid Login
                </p>
                <Input
                  className="border-zinc-700 bg-zinc-900/50"
                  autoComplete="off"
                  placeholder={
                    wbCreds.data?.login_is_set ? 'Leave empty to keep existing' : 'WesternBid login'
                  }
                  value={wbLogin}
                  onChange={(event) => setWbLogin(event.target.value)}
                />
              </div>

              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">
                  WesternBid API Key
                </p>
                <Input
                  className="border-zinc-700 bg-zinc-900/50"
                  type="password"
                  autoComplete="off"
                  placeholder={
                    wbCreds.data?.api_key_is_set ? 'Leave empty to keep existing' : 'WesternBid API key'
                  }
                  value={wbApiKey}
                  onChange={(event) => setWbApiKey(event.target.value)}
                />
              </div>

              <div className="flex items-center justify-between">
                <p className="text-xs text-zinc-400">
                  Used to poll sent parcels. Both values are stored encrypted; never shown again.
                </p>
                <Button
                  className="bg-teal-600 text-white hover:bg-teal-500"
                  onClick={saveWbCredentials}
                  disabled={setWbCreds.isPending || !wbApiKey.trim() || !wbLogin.trim()}
                >
                  {setWbCreds.isPending ? 'Saving...' : 'Save Credentials'}
                </Button>
              </div>

              {wbMessage && <p className="text-xs text-teal-300">{wbMessage}</p>}
            </CardContent>
          </Card>
        )}

        <Card className="border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-zinc-100">Session</CardTitle>
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
