/**
 * OrderHub CRM — App Settings API client (ADDR-VAL-1)
 *
 * Owner-only management of global app-level API keys. The key is write-only:
 * reads return a masked { is_set, last4 } status and never the plaintext.
 */

import client from '@/api/client';
import type { ApiKeyStatus } from '@/types/addressValidation';
import type { FxSettings, FxSettingsUpdate } from '@/types/fx';
import type {
  WesternBidCredentialsStatus,
  WesternBidCredentialsUpdate,
} from '@/types/westernbid';

export const appSettingsApi = {
  getAddressValidationKey: async (): Promise<ApiKeyStatus> => {
    const { data } = await client.get<ApiKeyStatus>('/settings/address-validation');
    return data;
  },

  setAddressValidationKey: async (apiKey: string): Promise<ApiKeyStatus> => {
    const { data } = await client.put<ApiKeyStatus>('/settings/address-validation', {
      api_key: apiKey,
    });
    return data;
  },

  getWesternBidCredentials: async (): Promise<WesternBidCredentialsStatus> => {
    const { data } = await client.get<WesternBidCredentialsStatus>('/settings/westernbid');
    return data;
  },

  setWesternBidCredentials: async (
    payload: WesternBidCredentialsUpdate,
  ): Promise<WesternBidCredentialsStatus> => {
    const { data } = await client.put<WesternBidCredentialsStatus>(
      '/settings/westernbid',
      payload,
    );
    return data;
  },

  getFxSettings: async (): Promise<FxSettings> => {
    const { data } = await client.get<FxSettings>('/settings/fx');
    return data;
  },

  setFxSettings: async (payload: FxSettingsUpdate): Promise<FxSettings> => {
    const { data } = await client.put<FxSettings>('/settings/fx', payload);
    return data;
  },

  /** Revert to the auto-fetched NBU rate. A DELETE rather than a null in the PUT:
   *  clearing silently changes the rate every future shipment books at, so it is
   *  its own audited operation. */
  clearFxOverride: async (): Promise<FxSettings> => {
    const { data } = await client.delete<FxSettings>('/settings/fx/override');
    return data;
  },
};
