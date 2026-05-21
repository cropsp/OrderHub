/**
 * OrderHub CRM — DraftGenerator modal (S004-mcp-wrapper)
 *
 * Wraps useDraftJob in a Dialog. Two render modes:
 *  - ProgressPanel: while running / connecting / reprocessing / failed.
 *  - CornerPicker: when SSE emits review_required.
 *  - "Download Draft" final state: when state=ready.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useToastStore } from '@/components/ui/Toast';
import { attachmentsApi } from '@/api/attachments';
import { useDraftJob } from '@/hooks/useDraftJob';
import ProgressPanel from './ProgressPanel';
import CornerPicker from './CornerPicker';

interface DraftGeneratorProps {
  isOpen: boolean;
  onClose: () => void;
  orderId: string;
  photoAttachmentId: string;
  photoFilename: string;
}

export default function DraftGenerator({
  isOpen,
  onClose,
  orderId,
  photoAttachmentId,
  photoFilename,
}: DraftGeneratorProps) {
  const job = useDraftJob(orderId);
  const { addToast } = useToastStore();
  const [photoBlob, setPhotoBlob] = useState<Blob | null>(null);
  // Tracks the photoAttachmentId for which start() has already been called
  // during the current modal-open cycle. Prevents React.StrictMode dev
  // double-invoke of this effect from creating two IdlaserDraftJob rows
  // for a single user click. Reset on modal close. See S004-followup-1.
  const lastStartedRef = useRef<string | null>(null);

  // Kick off the job whenever the modal opens with a new photo id.
  useEffect(() => {
    if (!isOpen) {
      lastStartedRef.current = null;
      return;
    }
    if (lastStartedRef.current === photoAttachmentId) return;
    if (job.state !== 'idle' && job.state !== 'failed') return;
    lastStartedRef.current = photoAttachmentId;
    void job.start(photoAttachmentId);
    // Deliberately not depending on `job` itself — the hook's identity
    // is stable; including it would re-fire on every state change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, photoAttachmentId]);

  // Fetch the photo bytes once review_required is reached.
  useEffect(() => {
    if (job.state !== 'review_required') return;
    if (photoBlob) return;
    attachmentsApi
      .download(photoAttachmentId)
      .then(setPhotoBlob)
      .catch((err) => {
        addToast(`Failed to load photo: ${err.message ?? err}`, 'error');
      });
  }, [job.state, photoAttachmentId, photoBlob, addToast]);

  const handleClose = useCallback(() => {
    job.cancel();
    setPhotoBlob(null);
    onClose();
  }, [job, onClose]);

  const handleDownload = useCallback(async () => {
    if (!job.result) return;
    try {
      const blob = await attachmentsApi.download(job.result.resultAttachmentId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `draft_${job.jobId ?? 'result'}.dxf`);
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch {
      addToast('Failed to download DXF', 'error');
    }
  }, [job.result, job.jobId, addToast]);

  const showCornerPicker =
    job.state === 'review_required' && photoBlob && job.reviewContext;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Generate Draft from {photoFilename}</DialogTitle>
          <DialogDescription>
            {job.state === 'review_required'
              ? 'Pipeline needs help — drag the four corners onto the card.'
              : job.state === 'ready'
                ? 'Draft DXF generated successfully.'
                : job.state === 'failed'
                  ? 'Pipeline failed. You can retry below.'
                  : 'Running pipeline...'}
          </DialogDescription>
        </DialogHeader>

        {showCornerPicker ? (
          <CornerPicker
            imageBlob={photoBlob!}
            initialCorners={job.reviewContext!.bestGuessCorners}
            onSubmit={(corners) => {
              setPhotoBlob(null);
              void job.submitCorners(corners);
            }}
            onCancel={handleClose}
          />
        ) : (
          <ProgressPanel events={job.events} state={job.state} />
        )}

        <DialogFooter>
          {job.state === 'ready' && job.result && (
            <Button onClick={handleDownload}>
              <Download className="mr-2 size-4" />
              Download Draft
            </Button>
          )}
          {job.state === 'failed' && (
            <Button variant="outline" onClick={() => void job.retry()}>
              <RefreshCw className="mr-2 size-4" />
              Retry
            </Button>
          )}
          {job.state !== 'review_required' && (
            <Button variant="ghost" onClick={handleClose}>
              Close
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
