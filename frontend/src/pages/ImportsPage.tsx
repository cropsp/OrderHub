import React, { useState, useRef } from 'react';
import { 
  Upload, 
  FileText, 
  CheckCircle2, 
  AlertCircle, 
  ChevronRight, 
  Database,
  Info,
  Store as StoreIcon,
  Zap
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
  const selectedShop = etsyShops.find(s => s.id === selectedShopId);

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
      title="Data sync imports"
      description="Intelligence pipeline for synchronizing historical Etsy exports into your production database."
    >
      <div className="max-w-4xl mx-auto space-y-10">
        {!importMutation.isSuccess ? (
          <div className="grid gap-8 lg:grid-cols-5 animate-in fade-in slide-in-from-bottom-4 duration-700">
            {/* Step 1: Select Shop */}
            <Card className="lg:col-span-2 border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl rounded-2xl overflow-hidden relative group">
              <div className="absolute inset-0 bg-gradient-to-br from-teal-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <CardContent className="p-8 space-y-8 relative z-10">
                <div className="flex items-center gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-950 border border-zinc-800 text-teal-400 font-black text-xs shadow-inner">01</div>
                  <h2 className="text-sm font-black uppercase tracking-widest text-zinc-100">Target context</h2>
                </div>
                
                <p className="text-xs text-zinc-500 font-medium leading-relaxed">
                  Select the designated Etsy instance for this batch synchronization. Credentials will be verified on-the-fly.
                </p>

                <div className="space-y-4 pt-2">
                   <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 ml-1">Store identifier</p>
                   <Select value={selectedShopId} onValueChange={setSelectedShopId}>
                    <SelectTrigger className="w-full bg-zinc-950 border-zinc-800 h-12 rounded-xl focus:ring-teal-500/20 transition-all">
                      <SelectValue placeholder={isLoadingShops ? "Scanning..." : "Select instance"} />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-950 border-zinc-800 rounded-xl">
                      {etsyShops.map(shop => (
                        <SelectItem key={shop.id} value={shop.id} className="rounded-lg focus:bg-zinc-900">
                          <div className="flex items-center gap-3">
                            <div className="h-2.5 w-2.5 rounded-full shadow-[0_0_8px_rgba(0,0,0,0.5)]" style={{ backgroundColor: shop.color || '#f59e0b' }} />
                            <span className="text-sm font-semibold">{shop.name}</span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="rounded-xl border border-blue-500/10 bg-blue-500/5 p-5 flex gap-4 transition-all hover:bg-blue-500/10">
                  <Info className="h-5 w-5 text-blue-400 shrink-0" />
                  <p className="text-[11px] text-blue-300/80 leading-relaxed font-medium italic">
                    Security context: OrderHub uses cryptographic Sale ID hashing to prevent duplicates.
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Step 2: Upload */}
            <Card className={cn(
              "lg:col-span-3 border-zinc-800/60 transition-all duration-700 rounded-2xl overflow-hidden relative",
              selectedShopId ? "bg-zinc-900/20 backdrop-blur-md opacity-100 shadow-2xl" : "bg-zinc-900/5 opacity-40 grayscale blur-[1px] pointer-events-none"
            )}>
              <CardContent className="p-8 h-full flex flex-col relative z-10">
                <div className="flex items-center gap-4 mb-10">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-950 border border-zinc-800 text-teal-400 font-black text-xs shadow-inner">02</div>
                  <h2 className="text-sm font-black uppercase tracking-widest text-zinc-100">Dataset ingestion</h2>
                </div>

                <div 
                  className={cn(
                    "flex-1 border-2 border-dashed rounded-3xl flex flex-col items-center justify-center p-10 transition-all gap-5",
                    file ? "border-teal-500/40 bg-teal-500/5" : "border-zinc-800 bg-zinc-950 hover:border-teal-500/30 hover:bg-zinc-900/40 cursor-pointer"
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
                    "h-20 w-20 rounded-2xl flex items-center justify-center mb-2 shadow-2xl transition-transform duration-500",
                    file ? "bg-teal-500 shadow-teal-500/20 text-white scale-110" : "bg-zinc-900 border border-zinc-800 text-zinc-500 group-hover:scale-105"
                  )}>
                    {file ? <CheckCircle2 className="h-10 w-10 animate-in zoom-in-50 duration-300" /> : <Upload className="h-10 w-10" />}
                  </div>

                  <div className="text-center max-w-[200px]">
                    <p className="text-sm font-black text-zinc-100 tracking-tight">
                      {file ? file.name : "Select Etsy source"}
                    </p>
                    <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mt-2">
                      {file ? `${(file.size / 1024).toFixed(1)} KB` : "CSV format required"}
                    </p>
                  </div>

                  {file && (
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="text-[10px] font-black uppercase tracking-widest text-zinc-500 hover:text-red-400 hover:bg-red-400/5 rounded-lg"
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }}
                    >
                      Reset selection
                    </Button>
                  )}
                </div>

                <div className="mt-10">
                  <Button 
                    className="w-full bg-teal-600 hover:bg-teal-500 text-white font-black uppercase tracking-widest text-xs h-14 rounded-2xl shadow-xl shadow-teal-900/20 transition-all active:scale-95"
                    disabled={!file || importMutation.isPending}
                    onClick={handleUpload}
                  >
                    {importMutation.isPending ? "Syncing intelligence..." : "Execute sync protocol"}
                    {!importMutation.isPending && <Zap className="ml-3 h-4 w-4 fill-current" />}
                  </Button>
                  {importMutation.isError && (
                    <div className="mt-4 p-3 rounded-xl border border-red-500/20 bg-red-500/5 flex items-center justify-center gap-2 animate-in slide-in-from-top-1">
                      <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />
                      <p className="text-[11px] font-bold text-red-400 uppercase tracking-tighter">
                        {importMutation.error instanceof Error ? importMutation.error.message : "Protocol error. Verify data structure."}
                      </p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <Card className="border-teal-500/20 bg-zinc-900/20 backdrop-blur-md shadow-[0_0_80px_-20px_rgba(20,184,166,0.3)] rounded-3xl overflow-hidden animate-in zoom-in-95 duration-500">
            <CardContent className="p-16 flex flex-col items-center text-center">
              <div className="h-24 w-24 rounded-3xl bg-teal-500 shadow-2xl shadow-teal-500/40 flex items-center justify-center mb-8 rotate-3 transition-transform hover:rotate-0 duration-500">
                <CheckCircle2 className="h-12 w-12 text-white" />
              </div>
              
              <h2 className="text-3xl font-black text-zinc-100 tracking-tight mb-3">Sync finalized.</h2>
              <p className="text-sm text-zinc-500 max-w-sm mb-12 font-medium">
                The extraction pipeline has completed. Data for <span className="text-zinc-200 font-bold">{selectedShop?.name}</span> is now consistent.
              </p>

              <div className="grid grid-cols-2 gap-8 w-full max-w-xl mb-12">
                <div className="bg-zinc-950 border border-zinc-800 p-8 rounded-3xl relative group overflow-hidden">
                  <div className="absolute inset-0 bg-teal-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />
                  <p className="text-5xl font-black text-teal-500 tracking-tighter relative z-10">{importMutation.data?.imported || 0}</p>
                  <p className="text-[10px] uppercase tracking-[0.2em] font-black text-zinc-600 mt-3 relative z-10">Ingested records</p>
                </div>
                <div className="bg-zinc-950 border border-zinc-800 p-8 rounded-3xl relative group overflow-hidden">
                  <div className="absolute inset-0 bg-zinc-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />
                  <p className="text-5xl font-black text-zinc-500 tracking-tighter relative z-10">{importMutation.data?.skipped || 0}</p>
                  <p className="text-[10px] uppercase tracking-[0.2em] font-black text-zinc-600 mt-3 relative z-10">Cached matches</p>
                </div>
              </div>

              {importMutation.data?.errors && importMutation.data.errors.length > 0 && (
                 <div className="w-full max-w-xl mb-12 text-left bg-zinc-950/50 border border-zinc-800 rounded-3xl p-6">
                    <p className="text-[10px] font-black text-red-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                       <AlertCircle size={14} /> Exceptions caught:
                    </p>
                    <div className="space-y-2 max-h-40 overflow-auto pr-4 scrollbar-thin scrollbar-thumb-zinc-800">
                        {importMutation.data.errors.map((err, idx) => (
                           <div key={idx} className="text-[11px] text-zinc-500 font-medium py-1.5 border-b border-white/5 last:border-0">• {err.detail || "Data integrity mismatch"}</div>
                        ))}
                    </div>
                 </div>
              )}

              <div className="flex flex-col sm:flex-row gap-4 w-full justify-center">
                <Button 
                  variant="ghost" 
                  className="px-8 h-12 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest transition-all"
                  onClick={handleReset}
                >
                  New sync session
                </Button>
                <Button 
                  className="px-8 h-12 bg-zinc-100 text-zinc-950 hover:bg-white rounded-xl font-bold uppercase text-[10px] tracking-widest transition-all shadow-xl shadow-white/5"
                  asChild
                >
                  <a href="/orders">View command console</a>
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        <section className="pt-10">
          <div className="flex items-center gap-4 mb-8">
            <div className="h-px flex-1 bg-zinc-800/60" />
            <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-zinc-900/50 border border-zinc-800">
               <Database className="h-3.5 w-3.5 text-zinc-500" />
               <span className="text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500">Related infrastructure</span>
            </div>
            <div className="h-px flex-1 bg-zinc-800/60" />
          </div>
          
          <div className="grid gap-6 sm:grid-cols-2">
            <a href="/shops" className="p-6 rounded-2xl border border-zinc-800/40 bg-zinc-900/20 backdrop-blur-sm flex items-center justify-between group transition-all hover:bg-zinc-900/60 hover:border-zinc-700 hover:shadow-2xl hover:shadow-black/20">
              <div className="flex items-center gap-4">
                 <div className="size-10 rounded-xl bg-zinc-950 border border-zinc-800 flex items-center justify-center transition-colors group-hover:border-teal-500/40">
                    <StoreIcon className="h-5 w-5 text-zinc-500 group-hover:text-teal-400 transition-colors" />
                 </div>
                 <div className="flex flex-col">
                    <span className="text-sm font-bold text-zinc-200 tracking-tight">Shop configurations</span>
                    <span className="text-[10px] font-bold text-zinc-600 uppercase tracking-tighter">Manage API keys</span>
                 </div>
              </div>
              <ChevronRight className="h-5 w-5 text-zinc-700 group-hover:text-zinc-400 transition-colors" />
            </a>
            
            <div className="p-6 rounded-2xl border border-zinc-800/40 bg-zinc-900/20 backdrop-blur-sm flex items-center justify-between group transition-all hover:bg-zinc-900/60 hover:border-zinc-700 hover:shadow-2xl hover:shadow-black/20 cursor-pointer">
              <div className="flex items-center gap-4">
                 <div className="size-10 rounded-xl bg-zinc-950 border border-zinc-800 flex items-center justify-center transition-colors group-hover:border-blue-500/40">
                    <FileText className="h-5 w-5 text-zinc-500 group-hover:text-blue-400 transition-colors" />
                 </div>
                 <div className="flex flex-col">
                    <span className="text-sm font-bold text-zinc-200 tracking-tight">Audit logs</span>
                    <span className="text-[10px] font-bold text-zinc-600 uppercase tracking-tighter">Sync history</span>
                 </div>
              </div>
              <ChevronRight className="h-5 w-5 text-zinc-700 group-hover:text-zinc-400 transition-colors" />
            </div>
          </div>
        </section>
      </div>
    </ShellPage>
  );
}
