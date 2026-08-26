import { useState } from 'react';
import { ChevronDown, ChevronRight, Plus } from 'lucide-react';

import { formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import {
  useAddCaseNote,
  useCreateCase,
  useOrderCases,
  useUpdateCase,
} from '@/hooks/useOrderCases';
import {
  CASE_STATUSES,
  CASE_TYPES,
  caseStatusLabel,
  caseTypeLabel,
  isOverdue,
} from '@/types/orderCase';
import type { CaseStatus, CaseType, OrderCase } from '@/types/orderCase';

/**
 * Per-order case tracker (CASE-1) — the ninth `detail/` sub-component.
 *
 * Owns its own query rather than reading cases off `OrderDetail`, the way
 * `AttachmentManager` does. Rendered only for OWNER/MANAGER; the endpoints are
 * role-gated server-side, so hiding the section is the UI half of one rule, not
 * the rule itself.
 *
 * Resolved cases stay listed here forever — they are the record of what
 * happened. Only the dashboard hides them.
 */

interface DetailCasesProps {
  orderId: string;
}

const STATUS_STYLES: Record<string, string> = {
  in_progress: 'border-teal-900/60 bg-teal-950/40 text-teal-300',
  waiting: 'border-amber-900/60 bg-amber-950/40 text-amber-300',
  resolved: 'border-zinc-700 bg-zinc-800/60 text-zinc-400',
};

const FALLBACK_STATUS_STYLE = 'border-zinc-700 bg-zinc-800/60 text-zinc-300';

const FIELD_CLASS =
  'w-full bg-zinc-950/50 border border-zinc-800 rounded-lg p-2.5 text-sm text-zinc-200 ' +
  'placeholder:text-zinc-600 focus:outline-none focus:border-teal-500/30 transition-all';

function DueBadge({ dueAt, status }: { dueAt: string | null; status: string }) {
  if (!dueAt) return null;
  // A resolved case is never "late" — the deadline stopped mattering when it
  // closed, and a red badge on a closed case is noise.
  const late = status !== 'resolved' && isOverdue(dueAt);
  return (
    <span
      data-testid="case-due"
      className={cn(
        'rounded px-1.5 py-0.5 text-[11px] tabular-nums',
        late ? 'bg-red-950/60 text-red-300' : 'text-zinc-500',
      )}
    >
      до {formatDateTime(dueAt)}
    </span>
  );
}

function CaseTimeline({ item }: { item: OrderCase }) {
  if (item.notes.length === 0) {
    return <p className="px-1 py-2 text-[11px] text-zinc-600">Нотаток ще немає</p>;
  }

  return (
    <div className="space-y-2.5 py-2">
      {item.notes.map((note) => {
        // The discriminator column, not a prefix parsed out of the text.
        const isSystem = note.kind === 'system';
        return (
          <div
            key={note.id}
            data-testid={isSystem ? 'case-note-system' : 'case-note-comment'}
            className={cn('flex flex-col gap-0.5', isSystem && 'opacity-70')}
          >
            <p
              className={cn(
                'text-sm',
                isSystem ? 'italic text-zinc-500' : 'text-zinc-300',
              )}
            >
              {note.text}
            </p>
            <p className="text-[11px] text-zinc-600">
              {note.author_name || 'Система'} · {formatDateTime(note.created_at)}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function CaseRow({ item, orderId }: { item: OrderCase; orderId: string }) {
  const [open, setOpen] = useState(false);
  const [noteText, setNoteText] = useState('');
  // Resolving asks for an optional summary first. Inline rather than
  // window.prompt: the native dialog ignores the theme and browsers are free to
  // suppress it outright, which would silently resolve cases with no summary.
  const [resolving, setResolving] = useState(false);
  const [summary, setSummary] = useState('');

  const updateCase = useUpdateCase(orderId);
  const addNote = useAddCaseNote(orderId);

  const Chevron = open ? ChevronDown : ChevronRight;
  const late = item.status !== 'resolved' && isOverdue(item.due_at);

  const cancelResolve = () => {
    setResolving(false);
    setSummary('');
  };

  const handleStatusChange = (next: CaseStatus) => {
    // Rule 9: closing asks for an optional summary. Every other transition is
    // immediate — only a close has a "why" worth writing down.
    if (next === 'resolved') {
      setResolving(true);
      return;
    }
    // Picking anything else abandons a summary in progress, so the box does
    // not linger over a case that is no longer being closed.
    cancelResolve();
    if (next === item.status) return;
    updateCase.mutate({ caseId: item.id, payload: { status: next } });
  };

  const confirmResolve = () => {
    const note = summary.trim();
    updateCase.mutate(
      {
        caseId: item.id,
        payload: { status: 'resolved', ...(note ? { resolution_note: note } : {}) },
      },
      {
        onSuccess: () => {
          setResolving(false);
          setSummary('');
        },
      },
    );
  };

  const handleAddNote = () => {
    const text = noteText.trim();
    if (!text) return;
    addNote.mutate({ caseId: item.id, text }, { onSuccess: () => setNoteText('') });
  };

  return (
    <div
      data-testid="case-row"
      className={cn(
        'border-b border-zinc-800/60 last:border-b-0 py-2.5',
        item.status === 'resolved' && 'opacity-60',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <Chevron className="h-3.5 w-3.5 shrink-0 text-zinc-500" aria-hidden />
          <span className="shrink-0 rounded border border-zinc-700 bg-zinc-800/60 px-1.5 py-0.5 text-[11px] text-zinc-300">
            {caseTypeLabel(item.case_type)}
          </span>
          <span
            className={cn(
              'min-w-0 truncate text-sm',
              late ? 'font-semibold text-red-300' : 'text-zinc-200',
            )}
          >
            {item.title}
          </span>
        </button>

        <DueBadge dueAt={item.due_at} status={item.status} />

        <select
          aria-label="Статус"
          value={resolving ? 'resolved' : item.status}
          disabled={updateCase.isPending}
          onChange={(e) => handleStatusChange(e.target.value as CaseStatus)}
          className={cn(
            'shrink-0 rounded border px-1.5 py-0.5 text-[11px]',
            STATUS_STYLES[item.status] ?? FALLBACK_STATUS_STYLE,
          )}
        >
          {CASE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {caseStatusLabel(s)}
            </option>
          ))}
        </select>
      </div>

      {item.next_action && (
        <p className="mt-1 pl-6 text-[11px] text-zinc-500">→ {item.next_action}</p>
      )}

      {resolving && (
        <div className="mt-2 flex items-start gap-2 pl-6">
          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Підсумок (необовʼязково)…"
            rows={2}
            aria-label="Підсумок"
            className={cn(FIELD_CLASS, 'resize-none')}
          />
          <button
            type="button"
            onClick={confirmResolve}
            disabled={updateCase.isPending}
            className="shrink-0 rounded-lg border border-teal-500/30 bg-teal-500/10 px-3 py-2 text-xs font-semibold text-teal-300 transition-colors hover:bg-teal-500/20 disabled:opacity-40"
          >
            Вирішити
          </button>
          <button
            type="button"
            onClick={cancelResolve}
            className="shrink-0 rounded-lg border border-zinc-800 px-3 py-2 text-xs font-semibold text-zinc-400 transition-colors hover:text-zinc-200"
          >
            Скасувати
          </button>
        </div>
      )}

      {open && (
        <div className="mt-2 pl-6">
          <CaseTimeline item={item} />

          {item.resolution_note && (
            <p className="mb-2 rounded border border-zinc-800/60 bg-zinc-950/40 p-2 text-[11px] text-zinc-400">
              Підсумок: {item.resolution_note}
            </p>
          )}

          <div className="flex items-start gap-2">
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Додати нотатку…"
              rows={2}
              aria-label="Додати нотатку"
              className={cn(FIELD_CLASS, 'resize-none')}
            />
            <button
              type="button"
              onClick={handleAddNote}
              disabled={addNote.isPending || !noteText.trim()}
              className="shrink-0 rounded-lg border border-teal-500/30 bg-teal-500/10 px-3 py-2 text-xs font-semibold text-teal-300 transition-colors hover:bg-teal-500/20 disabled:opacity-40"
            >
              Додати
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function CreateCaseForm({
  orderId,
  onDone,
}: {
  orderId: string;
  onDone: () => void;
}) {
  const [caseType, setCaseType] = useState<CaseType>('return');
  const [title, setTitle] = useState('');
  const [nextAction, setNextAction] = useState('');
  const [dueAt, setDueAt] = useState('');

  const createCase = useCreateCase(orderId);

  const submit = () => {
    const trimmed = title.trim();
    if (!trimmed) return;
    createCase.mutate(
      {
        case_type: caseType,
        title: trimmed,
        next_action: nextAction.trim() || null,
        // datetime-local has no zone; the browser's own offset is the right
        // reading of what the manager typed.
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
      },
      {
        onSuccess: () => {
          setTitle('');
          setNextAction('');
          setDueAt('');
          onDone();
        },
      },
    );
  };

  return (
    <div
      data-testid="case-create-form"
      className="mt-3 space-y-2 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3"
    >
      <div className="flex gap-2">
        <select
          aria-label="Тип"
          value={caseType}
          onChange={(e) => setCaseType(e.target.value as CaseType)}
          className={cn(FIELD_CLASS, 'w-auto shrink-0')}
        >
          {CASE_TYPES.map((t) => (
            <option key={t} value={t}>
              {caseTypeLabel(t)}
            </option>
          ))}
        </select>
        <input
          aria-label="Заголовок"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Що сталося?"
          className={FIELD_CLASS}
        />
      </div>
      <div className="flex gap-2">
        <input
          aria-label="Наступний крок"
          value={nextAction}
          onChange={(e) => setNextAction(e.target.value)}
          placeholder="Наступний крок (необовʼязково)"
          className={FIELD_CLASS}
        />
        <input
          aria-label="Дедлайн"
          type="datetime-local"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          className={cn(FIELD_CLASS, 'w-auto shrink-0')}
        />
      </div>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onDone}
          className="rounded-lg px-3 py-1.5 text-xs text-zinc-400 transition-colors hover:text-zinc-200"
        >
          Скасувати
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={createCase.isPending || !title.trim()}
          className="rounded-lg border border-teal-500/30 bg-teal-500/10 px-3 py-1.5 text-xs font-semibold text-teal-300 transition-colors hover:bg-teal-500/20 disabled:opacity-40"
        >
          Створити
        </button>
      </div>
    </div>
  );
}

export function DetailCases({ orderId }: DetailCasesProps) {
  const [creating, setCreating] = useState(false);
  const { data: cases, isLoading } = useOrderCases(orderId);

  const openCount = (cases ?? []).filter((c) => c.status !== 'resolved').length;

  return (
    <div
      data-testid="detail-cases"
      className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-4 shadow-sm"
    >
      <div className="mb-3 flex items-center gap-2 px-1">
        <h3 className="text-sm font-semibold text-zinc-100">Питання</h3>
        {openCount > 0 && (
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-zinc-300">
            {openCount}
          </span>
        )}
        <button
          type="button"
          onClick={() => setCreating((v) => !v)}
          className="ml-auto flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-teal-400 transition-colors hover:text-teal-300"
        >
          <Plus className="h-3 w-3" aria-hidden />
          питання
        </button>
      </div>

      {isLoading ? (
        <p className="px-1 text-[11px] text-zinc-600">Завантаження…</p>
      ) : (cases ?? []).length === 0 ? (
        <p className="px-1 text-[11px] text-zinc-600">
          Питань немає — із цим замовленням усе спокійно
        </p>
      ) : (
        <div>
          {(cases ?? []).map((item) => (
            <CaseRow key={item.id} item={item} orderId={orderId} />
          ))}
        </div>
      )}

      {creating && (
        <CreateCaseForm orderId={orderId} onDone={() => setCreating(false)} />
      )}
    </div>
  );
}
