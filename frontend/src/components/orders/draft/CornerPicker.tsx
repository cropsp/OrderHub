/**
 * OrderHub CRM — Manual corner picker (S004-mcp-wrapper)
 *
 * Full photo background with 4 draggable corner markers in absolute
 * positioning. Native pointer events (no new lib). Coordinates are
 * tracked in DISPLAYED pixels relative to the container and converted
 * back to ORIGINAL-IMAGE pixels on submit using the loaded img's
 * naturalWidth/naturalHeight. Photo logic donor: idlaser/review_tool.html.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';

export interface CornerPickerProps {
  imageBlob: Blob;
  initialCorners: number[][]; // 4 × [x, y] in original-image px
  onSubmit: (corners: number[][]) => void;
  onCancel: () => void;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export default function CornerPicker({
  imageBlob,
  initialCorners,
  onSubmit,
  onCancel,
}: CornerPickerProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const objectUrl = useMemo(() => URL.createObjectURL(imageBlob), [imageBlob]);
  useEffect(() => () => URL.revokeObjectURL(objectUrl), [objectUrl]);

  // Markers are stored in DISPLAYED pixels (container-relative).
  const [markers, setMarkers] = useState<number[][]>([]);
  const dragIndex = useRef<number | null>(null);

  // Seed markers once the image has loaded and we know the natural size.
  const onImageLoad = () => {
    const img = imgRef.current;
    const container = containerRef.current;
    if (!img || !container) return;
    const rect = container.getBoundingClientRect();
    if (img.naturalWidth === 0) return;
    const sx = rect.width / img.naturalWidth;
    const sy = rect.height / img.naturalHeight;
    if (initialCorners.length === 4) {
      setMarkers(initialCorners.map(([x, y]) => [x * sx, y * sy]));
    } else {
      // Evenly-spaced rectangle at 10/90% as the fallback (OQ-5).
      setMarkers([
        [rect.width * 0.1, rect.height * 0.1],
        [rect.width * 0.9, rect.height * 0.1],
        [rect.width * 0.9, rect.height * 0.9],
        [rect.width * 0.1, rect.height * 0.9],
      ]);
    }
  };

  const onPointerDown = (i: number) => (e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragIndex.current = i;
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const container = containerRef.current;
    if (dragIndex.current === null || !container) return;
    const rect = container.getBoundingClientRect();
    const x = clamp(e.clientX - rect.left, 0, rect.width);
    const y = clamp(e.clientY - rect.top, 0, rect.height);
    const i = dragIndex.current;
    setMarkers((m) => m.map((p, idx) => (idx === i ? [x, y] : p)));
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (dragIndex.current !== null) {
      try {
        e.currentTarget.releasePointerCapture(e.pointerId);
      } catch {
        // releasePointerCapture throws if not captured on this element;
        // ignore — drag state is already cleared below.
      }
      dragIndex.current = null;
    }
  };

  const handleSubmit = () => {
    const img = imgRef.current;
    const container = containerRef.current;
    if (!img || !container) return;
    const rect = container.getBoundingClientRect();
    const sx = img.naturalWidth / rect.width;
    const sy = img.naturalHeight / rect.height;
    const cornersOriginal = markers.map(([x, y]) => [x * sx, y * sy]);
    onSubmit(cornersOriginal);
  };

  return (
    <div className="flex flex-col gap-3">
      <div
        ref={containerRef}
        data-testid="corner-picker-container"
        className="relative inline-block max-h-[60vh] overflow-hidden rounded border border-zinc-800"
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <img
          ref={imgRef}
          src={objectUrl}
          alt="Customer photo"
          className="block max-w-full max-h-[60vh] select-none"
          draggable={false}
          onLoad={onImageLoad}
        />
        {markers.map(([x, y], i) => (
          <div
            key={i}
            role="button"
            aria-label={`Corner ${i + 1}`}
            data-corner={i}
            onPointerDown={onPointerDown(i)}
            style={{ left: x - 12, top: y - 12 }}
            className="absolute size-6 rounded-full border-2 border-amber-400 bg-amber-400/30 cursor-grab touch-none"
          />
        ))}
      </div>

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={handleSubmit}>Submit corners</Button>
      </div>
    </div>
  );
}
