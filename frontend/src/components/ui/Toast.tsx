import { create } from 'zustand';
import { cn } from '@/lib/utils';
import { X, CheckCircle2, AlertCircle, Info } from 'lucide-react';

type ToastType = 'success' | 'error' | 'info';

interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastStore {
  toasts: Toast[];
  addToast: (message: string, type?: ToastType) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  addToast: (message, type = 'info') => {
    const id = crypto.randomUUID();
    set((state) => ({
      toasts: [...state.toasts, { id, message, type }],
    }));
    setTimeout(() => {
      set((state) => ({
        toasts: state.toasts.filter((t) => t.id !== id),
      }));
    }, 4000);
  },
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }));
  },
}));

export function Toaster() {
  const { toasts, removeToast } = useToastStore();

  return (
    <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-3 pointer-events-none">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onRemove={removeToast} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const icons = {
    success: <CheckCircle2 className="size-4 text-teal-400" />,
    error: <AlertCircle className="size-4 text-red-400" />,
    info: <Info className="size-4 text-zinc-400" />,
  };

  return (
    <div className={cn(
      "pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl border bg-zinc-900 shadow-2xl animate-in slide-in-from-right-10 fade-in duration-300",
      toast.type === 'success' ? "border-teal-500/20" : 
      toast.type === 'error' ? "border-red-500/20" : "border-zinc-800"
    )}>
      {icons[toast.type]}
      <p className="text-sm font-medium text-zinc-200">{toast.message}</p>
      <button 
        onClick={() => onRemove(toast.id)}
        className="ml-4 p-1 hover:bg-zinc-800 rounded-lg text-zinc-400 hover:text-zinc-300 transition-colors"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}
