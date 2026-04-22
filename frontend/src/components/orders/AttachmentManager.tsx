import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { 
  FileIcon, 
  Upload, 
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
import { useToastStore } from '@/components/ui/Toast';

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
  const { addToast } = useToastStore();

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    setIsUploading(true);
    try {
      for (const file of acceptedFiles) {
        await uploadMutation.mutateAsync({ orderId, file, type: 'mockup' });
      }
      addToast('Files uploaded successfully', 'success');
      await refetch();
    } catch (error) {
      console.error('Upload failed:', error);
      addToast('Failed to upload files', 'error');
    } finally {
      setIsUploading(false);
    }
  }, [orderId, uploadMutation, refetch, addToast]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ 
    onDrop,
    multiple: true
  });

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm('Are you sure you want to delete this file?')) {
      try {
        await deleteMutation.mutateAsync(id);
        addToast('File deleted', 'success');
      } catch (error) {
        addToast('Failed to delete file', 'error');
      }
    }
  };

  const handleDownload = async (attachmentId: string, fileName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const blob = await attachmentsApi.download(attachmentId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', fileName);
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download failed:', error);
      addToast('Failed to download file', 'error');
    }
  };

  return (
    <div className="space-y-3">
      {/* Ultra-Compact Horizontal Upload Zone */}
      <div 
        {...getRootProps()} 
        className={cn(
          "border border-dashed border-zinc-700 rounded-lg p-3 flex items-center justify-between gap-4 hover:border-teal-500/50 hover:bg-teal-500/5 transition-colors cursor-pointer group",
          isDragActive && "border-teal-500 bg-teal-500/5",
          isUploading && "pointer-events-none opacity-60"
        )}
      >
        <input {...getInputProps()} />
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-zinc-800 flex items-center justify-center group-hover:bg-teal-500/10 transition-colors shrink-0">
            {isUploading ? (
              <Loader2 className="size-4 text-teal-400 animate-spin" />
            ) : (
              <Upload size={16} className="text-zinc-500 group-hover:text-teal-400" />
            )}
          </div>
          <div className="flex flex-col">
            <span className="text-sm text-zinc-300 font-medium leading-none mb-1">
              {isDragActive ? 'Drop to upload' : 'Upload Production Files'}
            </span>
            <span className="text-xs text-zinc-500 leading-none">
              SVG, DXF, PNG or PDF
            </span>
          </div>
        </div>
        <span className="text-xs text-zinc-600 hidden sm:block">No size limit</span>
      </div>

      {/* File List */}
      <div className="space-y-3">
        {isFetching ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="size-6 text-zinc-700 animate-spin" />
          </div>
        ) : attachments?.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-xs text-zinc-600 font-medium italic">No files attached to this order yet.</p>
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
                    <div className="size-10 rounded-lg bg-zinc-800/50 flex items-center justify-center border border-white/[0.03]">
                      <Icon className="size-5 text-zinc-400 group-hover/item:text-teal-400" />
                    </div>
                    <div className="space-y-0.5">
                      <p className="text-sm font-bold text-zinc-200 truncate max-w-[200px]" title={file.file_name}>
                        {file.file_name}
                      </p>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-zinc-500 font-mono">
                          {(file.file_size / 1024).toFixed(1)} KB
                        </span>
                        <span className="text-zinc-700">•</span>
                        <span className="text-[10px] text-zinc-500">
                          {format(new Date(file.created_at), 'MMM dd, HH:mm')}
                        </span>
                        <Badge variant="outline" className="h-4 px-1 text-[8px] bg-zinc-800/40 text-zinc-500 border-none uppercase">
                          {file.attachment_type}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 opacity-0 group-hover/item:opacity-100 transition-opacity">
                    <Button 
                      size="icon-sm" 
                      variant="ghost" 
                      className="size-8 rounded-lg text-zinc-400 hover:text-teal-400 hover:bg-teal-400/10"
                      onClick={(e) => handleDownload(file.id, file.file_name, e)}
                    >
                      <Download className="size-4" />
                    </Button>
                    <Button 
                      size="icon-sm" 
                      variant="ghost" 
                      className="size-8 rounded-lg text-zinc-400 hover:text-red-400 hover:bg-red-400/10"
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
