/**
 * OrderHub CRM — Draft Jobs API client (S004-mcp-wrapper)
 *
 * Thin axios wrappers for the polling/status endpoint and SSE-stream
 * URL builders. SSE itself runs through @microsoft/fetch-event-source
 * inside useDraftJob (native EventSource can't POST nor send custom
 * Authorization headers — OQ-9 b).
 */

import client from '@/api/client';
import type { DraftJobStatusResponse } from '@/types/draftJob';

export const draftJobsApi = {
  status: async (
    orderId: string,
    jobId: string,
  ): Promise<DraftJobStatusResponse> => {
    const { data } = await client.get<DraftJobStatusResponse>(
      `/orders/${orderId}/draft-jobs/${jobId}/status`,
    );
    return data;
  },

  /**
   * URL for the generate-draft SSE endpoint. fetchEventSource POSTs the
   * photo_attachment_id body and consumes the SSE stream.
   */
  generateDraftUrl: (orderId: string): string =>
    `${client.defaults.baseURL ?? ''}/orders/${orderId}/generate-draft`,

  /** URL for the manual-corners SSE endpoint. */
  manualCornersUrl: (orderId: string, jobId: string): string =>
    `${client.defaults.baseURL ?? ''}/orders/${orderId}/draft-jobs/${jobId}/manual-corners`,
};
