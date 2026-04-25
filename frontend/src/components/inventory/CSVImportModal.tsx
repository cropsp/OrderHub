import { useState, useRef } from 'react'
import { Upload, FileSpreadsheet, AlertCircle, CheckCircle2, Loader2, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface CSVImportModalProps {
  isOpen: boolean
  onClose: () => void
  onPreview: (file: File) => Promise<any>
  onConfirm: (token: string) => Promise<any>
  title: string
  description: string
  templateColumns: string[]
}

export default function CSVImportModal({
  isOpen,
  onClose,
  onPreview,
  onConfirm,
  title,
  description,
  templateColumns
}: CSVImportModalProps) {
  const [step, setStep] = useState<'upload' | 'preview'>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [previewData, setPreviewData] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleReset = () => {
    setStep('upload')
    setFile(null)
    setPreviewData(null)
    setError(null)
    setIsLoading(false)
  }

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (!selectedFile) return
    
    setFile(selectedFile)
    setError(null)
    setIsLoading(true)
    
    try {
      const data = await onPreview(selectedFile)
      setPreviewData(data)
      setStep('preview')
    } catch (err: any) {
      // TODO: SEC-07 — backend now returns generic detail; reconsider message extraction.
      setError(err.response?.data?.detail || 'Failed to parse CSV file')
    } finally {
      setIsLoading(false)
    }
  }

  const handleConfirm = async () => {
    if (!previewData?.import_token) return
    
    setIsLoading(true)
    setError(null)
    
    try {
      await onConfirm(previewData.import_token)
      onClose()
      handleReset()
    } catch (err: any) {
      // TODO: SEC-07 — backend now returns generic detail; reconsider message extraction.
      setError(err.response?.data?.detail || 'Failed to confirm import')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl border-zinc-800 bg-zinc-950 text-zinc-100 p-0 overflow-hidden rounded-3xl">
        <DialogHeader className="p-6 border-b border-zinc-800">
          <DialogTitle className="text-xl font-bold tracking-tight">{title}</DialogTitle>
          <DialogDescription className="text-zinc-400">
            {step === 'upload' ? description : `Review ${previewData?.valid_count} valid entries before confirming.`}
          </DialogDescription>
        </DialogHeader>

        <div className="p-8">
          {step === 'upload' ? (
            <div 
              className={cn(
                "group relative flex flex-col items-center justify-center p-12 border-2 border-dashed border-zinc-800 rounded-2xl bg-zinc-900/10 transition-all cursor-pointer hover:border-teal-500/40 hover:bg-teal-500/5",
                isLoading && "pointer-events-none opacity-50"
              )}
              onClick={() => fileInputRef.current?.click()}
            >
              <input 
                type="file" 
                accept=".csv" 
                className="hidden" 
                ref={fileInputRef}
                onChange={handleFileSelect}
              />
              <div className="size-16 rounded-2xl bg-zinc-900 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                {isLoading ? <Loader2 className="size-8 text-teal-400 animate-spin" /> : <Upload className="size-8 text-zinc-500 group-hover:text-teal-400" />}
              </div>
              <p className="text-sm font-medium text-zinc-300">Click to upload or drag & drop</p>
              <p className="text-xs text-zinc-500 mt-2">Required columns: {templateColumns.join(', ')}</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Summary Stats */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-xl border border-teal-500/10 bg-teal-500/5 flex items-center gap-3">
                  <CheckCircle2 className="size-5 text-teal-400" />
                  <div>
                    <p className="text-[10px] font-bold text-teal-500 uppercase tracking-wider">Valid Rows</p>
                    <p className="text-xl font-bold text-teal-100">{previewData.valid_count}</p>
                  </div>
                </div>
                <div className={cn(
                  "p-4 rounded-xl border flex items-center gap-3",
                  previewData.invalid_count > 0 ? "border-red-500/20 bg-red-500/5" : "border-zinc-800 bg-zinc-900/20"
                )}>
                  <AlertCircle className={cn("size-5", previewData.invalid_count > 0 ? "text-red-400" : "text-zinc-500")} />
                  <div>
                    <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">Errors found</p>
                    <p className={cn("text-xl font-bold", previewData.invalid_count > 0 ? "text-red-400" : "text-zinc-400")}>
                      {previewData.invalid_count}
                    </p>
                  </div>
                </div>
              </div>

              {/* Preview Table */}
              <div className="rounded-xl border border-zinc-800 overflow-hidden">
                <div className="bg-zinc-900/50 px-4 py-2 border-b border-zinc-800">
                  <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Sample (First 5 Rows)</span>
                </div>
                <Table>
                  <TableHeader className="bg-white/[0.01]">
                    <TableRow className="border-zinc-800 hover:bg-transparent">
                      {Object.keys(previewData.preview[0] || {}).filter(k => k !== 'variants' && k !== 'id' && k !== 'created_at' && k !== 'updated_at').map(key => (
                        <TableHead key={key} className="text-[10px] font-bold uppercase text-zinc-500 py-3">{key}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {previewData.preview.map((row: any, i: number) => (
                      <TableRow key={i} className="border-zinc-800 hover:bg-white/[0.02]">
                        {Object.entries(row).filter(([k]) => k !== 'variants' && k !== 'id' && k !== 'created_at' && k !== 'updated_at').map(([_, val]: any, j) => (
                          <TableCell key={j} className="text-xs text-zinc-300 py-3">{String(val)}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Error list if any */}
              {previewData.errors.length > 0 && (
                <div className="p-4 rounded-xl border border-red-500/20 bg-red-500/5 max-h-40 overflow-y-auto">
                  <p className="text-xs font-bold text-red-400 mb-2 uppercase tracking-tight">Validation Issues:</p>
                  <ul className="space-y-1">
                    {previewData.errors.map((err: any, i: number) => (
                      <li key={i} className="text-[11px] text-zinc-400 flex items-start gap-2">
                        <span className="text-red-500/60 mt-0.5">•</span>
                        <span>Row {err.row}: {err.reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="mt-4 flex items-center gap-2 p-3 rounded-lg border border-red-500/20 bg-red-500/5 text-xs text-red-400">
              <AlertCircle className="size-4" />
              {error}
            </div>
          )}
        </div>

        <DialogFooter className="bg-zinc-900/30 p-6 border-t border-zinc-800 gap-3">
          <Button 
            variant="ghost" 
            onClick={step === 'upload' ? onClose : handleReset}
            className="text-zinc-400 hover:text-zinc-100"
          >
            {step === 'upload' ? 'Cancel' : 'Change File'}
          </Button>
          {step === 'preview' && (
            <Button 
              onClick={handleConfirm}
              disabled={isLoading || previewData.valid_count === 0}
              className="bg-teal-600 hover:bg-teal-500 text-white shadow-lg"
            >
              {isLoading ? <Loader2 className="size-4 animate-spin mr-2" /> : <CheckCircle2 className="size-4 mr-2" />}
              Confirm & Import {previewData.valid_count} Items
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
