/**
 * OrderHub CRM — DraftGenerator progress panel (S004-mcp-wrapper)
 *
 * Renders the ordered pipeline stages with check marks driven by SSE
 * events. Mirrors the master-rule-9 event taxonomy.
 */

import { useMemo } from 'react';
import { CheckCircle2, Circle, Loader2, AlertCircle } from 'lucide-react';

import type { DraftEvent, DraftJobState } from '@/types/draftJob';

interface ProgressPanelProps {
  events: DraftEvent[];
  state: DraftJobState;
}

const STAGES: { eventType: string; label: string }[] = [
  { eventType: 'detect.classical.completed', label: 'Detecting card (classical)' },
  { eventType: 'detect.ml.completed', label: 'Detecting card (ML)' },
  { eventType: 'rectify.completed', label: 'Rectifying perspective' },
  { eventType: 'face.completed', label: 'Detecting face' },
  { eventType: 'eyes.completed', label: 'Detecting eyes' },
  { eventType: 'compose.completed', label: 'Composing layout' },
  { eventType: 'export.completed', label: 'Exporting DXF' },
];

export default function ProgressPanel({ events, state }: ProgressPanelProps) {
  const seenStages = useMemo(
    () => new Set(events.map((e) => e.type)),
    [events],
  );

  const errorEvent = useMemo(
    () => events.find((e) => e.type === 'error'),
    [events],
  );

  const isFailed = state === 'failed';
  const isRunning = state === 'running' || state === 'connecting' || state === 'reprocessing';

  return (
    <div className="space-y-3" role="list" aria-label="Pipeline stages">
      {STAGES.map((stage) => {
        const seen = seenStages.has(stage.eventType);
        const Icon = seen ? CheckCircle2 : isRunning ? Loader2 : Circle;
        return (
          <div
            key={stage.eventType}
            role="listitem"
            className="flex items-center gap-3 text-sm"
            data-stage={stage.eventType}
            data-seen={seen ? 'true' : 'false'}
          >
            <Icon
              className={`size-4 shrink-0 ${
                seen
                  ? 'text-teal-400'
                  : isRunning
                    ? 'text-zinc-400 animate-spin'
                    : 'text-zinc-700'
              }`}
            />
            <span className={seen ? 'text-zinc-200' : 'text-zinc-500'}>
              {stage.label}
            </span>
          </div>
        );
      })}

      {isFailed && errorEvent && (
        <div className="flex items-center gap-2 text-sm text-red-400 pt-2 border-t border-zinc-800">
          <AlertCircle className="size-4 shrink-0" />
          <span>
            {(errorEvent.payload.message as string) ?? 'Pipeline error'}
          </span>
        </div>
      )}
    </div>
  );
}
