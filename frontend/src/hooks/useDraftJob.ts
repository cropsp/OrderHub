/**
 * OrderHub CRM — useDraftJob hook (S004-mcp-wrapper)
 *
 * Owns the client-side state machine for an IdlaserDraftJob plus its SSE
 * subscription. fetchEventSource (not native EventSource) is used because
 * we POST and we send Authorization: Bearer in headers — OQ-9 (b).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';

import { getAccessToken } from '@/api/client';
import { draftJobsApi } from '@/api/draftJobsApi';
import type {
  DraftEvent,
  DraftJobState,
  ReviewContext,
} from '@/types/draftJob';

interface StartResult {
  resultAttachmentId: string;
}

export interface UseDraftJobResult {
  state: DraftJobState;
  events: DraftEvent[];
  result: StartResult | null;
  reviewContext: ReviewContext | null;
  error: string | null;
  jobId: string | null;
  start: (photoAttachmentId: string) => Promise<void>;
  submitCorners: (corners: number[][]) => Promise<void>;
  cancel: () => void;
  retry: () => Promise<void>;
}

function parseEventData(raw: string): {
  payload: Record<string, unknown>;
  timestamp: string;
  job_state: DraftEvent['job_state'];
} {
  try {
    return JSON.parse(raw);
  } catch {
    return { payload: {}, timestamp: '', job_state: 'running' };
  }
}

export function useDraftJob(orderId: string): UseDraftJobResult {
  const [state, setState] = useState<DraftJobState>('idle');
  const [events, setEvents] = useState<DraftEvent[]>([]);
  const [result, setResult] = useState<StartResult | null>(null);
  const [reviewContext, setReviewContext] = useState<ReviewContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const photoAttachmentIdRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const consumeStream = useCallback(
    async (url: string, body: object) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const token = getAccessToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      };
      if (token) headers.Authorization = `Bearer ${token}`;

      setError(null);

      try {
        await fetchEventSource(url, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
          signal: controller.signal,
          openWhenHidden: true,
          onmessage(msg) {
            const parsed = parseEventData(msg.data);
            const evt: DraftEvent = {
              type: msg.event || 'message',
              payload: parsed.payload,
              timestamp: parsed.timestamp,
              job_state: parsed.job_state,
            };
            setEvents((prev) => [...prev, evt]);

            if (evt.type === 'job.started') {
              const id = evt.payload.job_id as string | undefined;
              if (id) setJobId(id);
              setState('running');
              return;
            }
            if (evt.type === 'export.completed') {
              const resultAttachmentId =
                evt.payload.result_attachment_id as string | undefined;
              if (resultAttachmentId) {
                setResult({ resultAttachmentId });
              }
              setState('ready');
              controller.abort();
              return;
            }
            if (evt.type === 'review_required') {
              const corners =
                (evt.payload.best_guess_corners as number[][] | null) ?? [];
              const reason = (evt.payload.reason as string) ?? '';
              const rectifiedPreviewUrl =
                (evt.payload.rectified_preview_url as string | null) ?? null;
              setReviewContext({
                bestGuessCorners: corners,
                rectifiedPreviewUrl,
                reason,
              });
              setState('review_required');
              controller.abort();
              return;
            }
            if (evt.type === 'error') {
              const message = (evt.payload.message as string) ?? 'Pipeline error';
              setError(message);
              setState('failed');
              controller.abort();
              return;
            }
          },
          onerror(err) {
            // Throwing forces fetchEventSource to stop retrying.
            throw err;
          },
        });
      } catch (err) {
        if (controller.signal.aborted) {
          // Clean abort from a terminal event handler — not a real error.
          return;
        }
        const message = err instanceof Error ? err.message : 'Connection lost';
        setError(message);
        setState('failed');
      }
    },
    [],
  );

  const start = useCallback(
    async (photoAttachmentId: string) => {
      photoAttachmentIdRef.current = photoAttachmentId;
      setEvents([]);
      setResult(null);
      setReviewContext(null);
      setError(null);
      setJobId(null);
      setState('connecting');
      await consumeStream(draftJobsApi.generateDraftUrl(orderId), {
        photo_attachment_id: photoAttachmentId,
      });
    },
    [orderId, consumeStream],
  );

  const submitCorners = useCallback(
    async (corners: number[][]) => {
      if (!jobId) {
        setError('No job in progress');
        return;
      }
      setState('reprocessing');
      setReviewContext(null);
      await consumeStream(
        draftJobsApi.manualCornersUrl(orderId, jobId),
        { corners },
      );
    },
    [orderId, jobId, consumeStream],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState('cancelled');
  }, []);

  const retry = useCallback(async () => {
    const photoId = photoAttachmentIdRef.current;
    if (!photoId) return;
    await start(photoId);
  }, [start]);

  return {
    state,
    events,
    result,
    reviewContext,
    error,
    jobId,
    start,
    submitCorners,
    cancel,
    retry,
  };
}
