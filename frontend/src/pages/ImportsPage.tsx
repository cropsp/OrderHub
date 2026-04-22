import React, { useState, useRef } from 'react';
import { 
  Upload, 
  FileText, 
  CheckCircle2, 
  AlertCircle, 
  ChevronRight, 
  Database,
  ArrowRight,
  Info
} from 'lucide-react';
import ShellPage from './ShellPage';
import { useShops } from '@/hooks/useShops';
import { useImportEtsyCsv } from '@/hooks/useImports';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';

export default function ImportsPage() {
  const [selectedShopId, setSelectedShopId] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const { data: shops, isLoading: isLoadingShops } = useShops();
  const importMutation = useImportEtsyCsv();
  
  const etsyShops = shops?.filter(s => s.platform?.toLowerCase() === 'etsy') || [];

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = () => {
    if (!selectedShopId || !file) return;
    importMutation.mutate({ shopId: selectedShopId, file });
  };

  const handleReset = () => {
    setFile(null);
    importMutation.reset();
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <ShellPage
      title="Data Imports"
      description="Synchronize orders from Etsy CSV exports into your database."
    >
      <div className="max-w-4xl mx-auto space-y-8">
        {!importMutation.isSuccess ? (
          <div className="grid gap-8 lg:grid-cols-5">
            {/* Step 1: Select Shop */}
            <Card className="lg:col-span-2 border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm shadow-xl">
              <CardContent className="p-6 space-y-6">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-500/10 text-teal-400 font-bold text-sm">1</div>
                  <h2 className="text-lg font-semibold text-zinc-100">Target Shop</h2>
                </div>
                
                <p className="text-sm text-zinc-400 leading-relaxed">
                  Select the Etsy store associated with the CSV file you are importing.
                </p>

                <Select value={selectedShopId} onValueChange={setSelectedShopId}>
                  <SelectTrigger className="w-full bg-zinc-950/50 border-zinc-800">
                    <SelectValue placeholder={isLoadingShops ? "Loading shops..." : "Select an Etsy shop"} />
                  </SelectTrigger>
                  <SelectContent className="bg-zinc-900 border-zinc-800">
                    {etsyShops.map(shop => (
                      <SelectItem key={shop.id} value={shop.id}>
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-2 rounded-full" style={{ backgroundColor: shop.color || '#f59e0b' }} />
                          {shop.name}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <div className="rounded-xl border border-blue-500/10 bg-blue-500/5 p-4 flex gap-3">
                  <Info className="h-5 w-5 text-blue-400 shrink-0" />
                  <p className="text-xs text-blue-300 leading-relaxed">
                    OrderHub uses the <strong>Sale ID</strong> to prevent duplicate entries. You can safely upload the same file multiple times.
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Step 2: Upload */}
            <Card className={cn(
              "lg:col-span-3 border-zinc-800/60 transition-all duration-300",
              selectedShopId ? "bg-zinc-900/40 opacity-100" : "bg-zinc-900/20 opacity-50 grayscale pointer-events-none"
            )}>
              <CardContent className="p-6 h-full flex flex-col">
                <div className="flex items-center gap-3 mb-6">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-500/10 text-teal-400 font-bold text-sm">2</div>
                  <h2 className="text-lg font-semibold text-zinc-100">Upload CSV</h2>
                </div>

                <div 
                  className={cn(
                    "flex-1 border-2 border-dashed rounded-2xl flex flex-col items-center justify-center p-8 transition-all gap-4",
                    file ? "border-teal-500/40 bg-teal-500/5" : "border-zinc-800 bg-zinc-950/30 hover:border-zinc-700 hover:bg-zinc-900/40 cursor-pointer"
                  )}
                  onClick={() => !file && fileInputRef.current?.click()}
                >
                  <input 
                    type="file" 
                    className="hidden" 
                    accept=".csv" 
                    ref={fileInputRef}
                    onChange={handleFileChange}
                  />
                  
                  <div className={cn(
                    "h-16 w-16 rounded-2xl flex items-center justify-center mb-2",
                    file ? "bg-teal-500/20 text-teal-400" : "bg-zinc-800 text-zinc-500"
                  )}>
                    {file ? <FileText className="h-8 w-8" /> : <Upload className="h-8 w-8" />}
                  </div>

                  <div className="text-center">
                    <p className="text-sm font-medium text-zinc-200">
                      {file ? file.name : "Drag and drop your Etsy CSV file here"}
                    </p>
                    <p className="text-xs text-zinc-500 mt-1">
                      {file ? `${(file.size / 1024).toFixed(1)} KB` : "Supports standard Etsy Orders CSV format"}
                    </p>
                  </div>

                  {file && (
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="text-zinc-400 hover:text-red-400 hover:bg-red-400/5"
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }}
                    >
                      Clear selection
                    </Button>
                  )}
                </div>

                <div className="mt-8">
                  <Button 
                    className="w-full bg-teal-600 hover:bg-teal-500 text-white font-bold h-12"
                    disabled={!file || importMutation.isPending}
                    onClick={handleUpload}
                  >
                    {importMutation.isPending ? "Processing Data..." : "Run Import Workflow"}
                    {!importMutation.isPending && <ArrowRight className="ml-2 h-4 w-4" />}
                  </Button>
                  {importMutation.isError && (
                    <p className="text-center text-xs text-red-400 mt-3 flex items-center justify-center gap-1">
                      <AlertCircle className="h-3 w-3" />
                      {importMutation.error instanceof Error ? importMutation.error.message : "Import failed. Check file format."}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <Card className="border-teal-500/20 bg-teal-500/5 shadow-2xl animate-in zoom-in-95 duration-300">
            <CardContent className="p-12 flex flex-col items-center text-center">
              <div className="h-20 w-20 rounded-full bg-teal-500/20 flex items-center justify-center mb-6">
                <CheckCircle2 className="h-10 w-10 text-teal-400" />
              </div>
              
              <h2 className="text-3xl font-heading text-zinc-100 mb-2">Import Successful!</h2>
              <p className="text-zinc-400 max-w-md mb-10">
                The CSV file has been processed. New records have been added to your order pool.
              </p>

              <div className="grid grid-cols-2 gap-8 w-full max-w-lg mb-10">
                <div className="bg-zinc-900/50 p-6 rounded-2xl border border-zinc-800">
                  <p className="text-3xl font-bold text-teal-400">{importMutation.data?.imported || 0}</p>
                  <p className="text-xs uppercase tracking-widest font-bold text-zinc-500 mt-1">New Orders Created</p>
                </div>
                <div className="bg-zinc-900/50 p-6 rounded-2xl border border-zinc-800">
                  <p className="text-3xl font-bold text-zinc-400">{importMutation.data?.skipped || 0}</p>
                  <p className="text-xs uppercase tracking-widest font-bold text-zinc-500 mt-1">Skipped (Duplicates)</p>
                </div>
              </div>

              {importMutation.data?.errors && importMutation.data.errors.length > 0 && (
                 <div className="w-full max-w-lg mb-10 text-left">
                    <p className="text-xs font-bold text-red-400/80 uppercase tracking-widest mb-3 px-2">Rows with issues:</p>
                    <div className="bg-red-500/5 border border-red-500/10 rounded-xl p-4 max-h-40 overflow-auto">
                        {importMutation.data.errors.map((err, idx) => (
                           <p key={idx} className="text-xs text-red-300 mb-1 leading-relaxed">• {err.detail || "Unknown data issue"}</p>
                        ))}
                    </div>
                 </div>
              )}

              <div className="flex flex-col sm:flex-row gap-4 w-full justify-center">
                <Button 
                  variant="outline" 
                  className="border-zinc-800 bg-zinc-900 hover:bg-zinc-800"
                  onClick={handleReset}
                >
                  Import another file
                </Button>
                <Button 
                  className="bg-teal-600 hover:bg-teal-500 text-white"
                  asChild
                >
                  <a href="/orders">Go to Orders Pipeline</a>
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        <section className="pt-10">
          <div className="flex items-center gap-3 mb-6">
            <Database className="h-5 w-5 text-zinc-500" />
            <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-500">Related Activity</h3>
          </div>
          
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="p-4 rounded-xl border border-zinc-800/40 bg-zinc-900/20 flex items-center justify-between group cursor-pointer hover:bg-zinc-900/40 transition-colors">
              <div className="flex items-center gap-3">
                 <Store className="h-4 w-4 text-zinc-500 group-hover:text-teal-400 transition-colors" />
                 <span className="text-sm text-zinc-300">Shop Configurations</span>
              </div>
              <ChevronRight className="h-4 w-4 text-zinc-700" />
            </div>
            
            <div className="p-4 rounded-xl border border-zinc-800/40 bg-zinc-900/20 flex items-center justify-between group cursor-pointer hover:bg-zinc-900/40 transition-colors">
              <div className="flex items-center gap-3">
                 <FileText className="h-4 w-4 text-zinc-500 group-hover:text-teal-400 transition-colors" />
                 <span className="text-sm text-zinc-300">View Recent Audit Log</span>
              </div>
              <ChevronRight className="h-4 w-4 text-zinc-700" />
            </div>
          </div>
        </section>
      </div>
    </ShellPage>
  );
}

function Store({ className }: { className?: string }) {
  return (
    <svg 
      className={className} 
      xmlns="http://www.w3.org/2000/svg" 
      width="24" 
      height="24" 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round"
    >
      <path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7" />
      <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
      <path d="M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4" />
      <path d="M2 7h20" />
      <path d="M22 7v3a2 2 0 0 1-2 2v0a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 16 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 12 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 8 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 4 12v0a2 2 0 0 1-2-2V7" />
    </svg>
  );
}
