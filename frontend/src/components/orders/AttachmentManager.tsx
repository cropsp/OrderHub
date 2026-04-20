import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { 
  FileIcon, 
  UploadCloud, 
  X, 
  Download, 
  FileText, 
  ImageIcon, 
  FileCode,
  Loader2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useAttachments, useUploadAttachment, useDeleteAttachment } from '@/hooks/useAttachments';
import { attachmentsApi } from '@/api/attachments';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';

type AttachmentManagerProps = {
  orderId: string;
};

const getFileIcon = (mimeType: string) => {
  if (mimeType.startsWith('image/')) return ImageIcon;
  if (mimeType.includes('svg') || mimeType.includes('xml')) return FileCode;
  if (mimeType.includes('pdf')) return FileText;
  return FileIcon;
};

export default function AttachmentManager({ orderId }: AttachmentManagerProps) {
  const { data: attachments, isLoading: isFetching, refetch } = useAttachments(orderId);
  const uploadMutation = useUploadAttachment();
  const deleteMutation = useDeleteAttachment();
  const [isUploading, setIsUploading] = useState(false);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    setIsUploading(true);
    try {
      for (const file of acceptedFiles) {
        await uploadMutation.mutateAsync({ orderId, file, type: 'mockup' });
      }
      // Force refresh the list after all uploads
      await refetch();
    } catch (error) {
      console.error('Upload failed:', error);
    } finally {
      setIsUploading(false);
    }
  }, [orderId, uploadMutation, refetch]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ 
    onDrop,
    multiple: true
  });

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this file?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  const handleDownload = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    window.open(attachmentsApi.getDownloadUrl(id), '_blank');
  };

  return (
    <div className="space-y-6">
      {/* Upload Zone */}
      <div 
        {...getRootProps()} 
        className={cn(
          "relative border-2 border-dashed rounded-2xl p-8 transition-all cursor-pointer group",
          isDragActive 
            ? "border-teal-500 bg-teal-500/5" 
            : "border-slate-800 bg-slate-900/20 hover:border-slate-700 hover:bg-slate-900/30",
          isUploading && "pointer-events-none opacity-60"
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center justify-center text-center gap-3">
          <div className="size-12 rounded-full bg-slate-800 flex items-center justify-center group-hover:scale-110 transition-transform">
            {isUploading ? (
              <Loader2 className="size-6 text-teal-400 animate-spin" />
            ) : (
              <UploadCloud className="size-6 text-slate-400 group-hover:text-teal-400" />
            )}
          </div>
          <div className="space-y-1">
            <p className="text-sm font-bold text-slate-200">
              {isDragActive ? 'Drop to upload' : 'Drag & drop production files'}
            </p>
            <p className="text-xs text-slate-500">SVG, DXF, PNG or PDF (No size limit)</p>
          </div>
        </div>
      </div>

      {/* File List */}
      <div className="space-y-3">
        {isFetching ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="size-6 text-slate-700 animate-spin" />
          </div>
        ) : attachments?.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-xs text-slate-600 font-medium italic">No files attached to this order yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {attachments?.map((file) => {
              const Icon = getFileIcon(file.mime_type);
              return (
                <div 
                  key={file.id}
                  className="flex items-center justify-between p-4 rounded-xl bg-white/[0.02] border border-white/[0.03] hover:border-white/[0.08] hover:bg-white/[0.04] transition-all group/item"
                >
                  <div className="flex items-center gap-4">
                    <div className="size-10 rounded-lg bg-slate-800/50 flex items-center justify-center border border-white/[0.03]">
                      <Icon className="size-5 text-slate-400 group-hover/item:text-teal-400" />
                    </div>
                    <div className="space-y-0.5">
                      <p className="text-sm font-bold text-slate-200 truncate max-w-[200px]" title={file.file_name}>
                        {file.file_name}
                      </p>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-slate-500 font-mono">
                          {(file.file_size / 1024).toFixed(1)} KB
                        </span>
                        <span className="text-slate-700">•</span>
                        <span className="text-[10px] text-slate-500">
                          {format(new Date(file.created_at), 'MMM dd, HH:mm')}
                        </span>
                        <Badge variant="outline" className="h-4 px-1 text-[8px] bg-slate-800/40 text-slate-500 border-none uppercase">
                          {file.attachment_type}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 opacity-0 group-hover/item:opacity-100 transition-opacity">
                    <Button 
                      size="icon-sm" 
                      variant="ghost" 
                      className="size-8 rounded-lg text-slate-400 hover:text-teal-400 hover:bg-teal-400/10"
                      onClick={(e) => handleDownload(file.id, e)}
                    >
                      <Download className="size-4" />
                    </Button>
                    <Button 
                      size="icon-sm" 
                      variant="ghost" 
                      className="size-8 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-400/10"
                      onClick={(e) => handleDelete(file.id, e)}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
