/**
 * OrderHub CRM — App Settings API client (ADDR-VAL-1)
 *
 * Owner-only management of global app-level API keys. The key is write-only:
 * reads return a masked { is_set, last4 } status and never the plaintext.
 */

import client from '@/api/client';
import type { ApiKeyStatus } from '@/types/addressValidation';

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
};
