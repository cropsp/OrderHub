import { useRef, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Info,
  Receipt,
  Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useImportEtsyStatement } from '@/hooks/useImports';
import { formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Shop } from '@/types/common';

/**
 * STATEMENT-IMPORT — upload one monthly Etsy payment-account statement.
 *
 * Distinct from the order-CSV import beside it: that one creates orders, this
 * one prices them. It derives each order's exact `platform_fee` from the Fee +
 * fee-VAT lines and books advertising and listing fees to two monthly overhead
 * rows.
 *
 * Idempotent per calendar month — re-uploading replaces that period wholesale —
 * so the operator can safely re-run a month after Etsy re-issues a statement.
 */
export default function StatementImportTab({ shops }: { shops: Shop[] }) {
  const [selectedShopId, setSelectedShopId] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const importMutation = useImportEtsyStatement();

  const report = importMutation.data;
  const selectedShop = shops.find((s) => s.id === selectedShopId);

  const handleReset = () => {
    setFile(null);
    importMutation.reset();
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  if (report) {
    return (
      <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <Card className="border-teal-500/20 bg-zinc-900/20 backdrop-blur-md rounded-3xl overflow-hidden">
          <CardContent className="p-10 space-y-10">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="h-14 w-14 rounded-2xl bg-teal-500 shadow-2xl shadow-teal-500/30 flex items-center justify-center">
                  <CheckCircle2 className="h-7 w-7 text-white" />
                </div>
                <div>
                  <h2 className="text-2xl font-black text-zinc-100 tracking-tight">
                    {report.period} booked
                  </h2>
                  <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-500 mt-1">
                    {selectedShop?.name} · {report.source_filename}
                  </p>
                </div>
              </div>
              {report.identical_file && (
                <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 px-4 py-2.5 flex items-center gap-2">
                  <Info className="h-4 w-4 text-blue-400 shrink-0" />
                  <span className="text-[11px] font-bold text-blue-300">
                    Same file re-uploaded — nothing changed
                  </span>
                </div>
              )}
            </div>

            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                label="Order fees"
                value={`${report.orders_matched} matched`}
                sub={
                  report.orders_unmatched > 0
                    ? `${report.orders_unmatched} unmatched`
                    : 'all matched'
                }
                tone={report.orders_unmatched > 0 ? 'warn' : 'good'}
              />
              <Stat
                label="Advertising → overhead"
                value={formatMoney(report.ads_overhead_amount)}
                sub="Etsy Ads + Offsite + VAT"
              />
              <Stat
                label="Account fees → overhead"
                value={formatMoney(report.account_fee_overhead_amount)}
                sub="Listing, auto-renew + VAT"
              />
              <Stat
                label="Statement lines"
                value={String(report.lines_imported)}
                sub={
                  report.lines_replaced > 0
                    ? `replaced ${report.lines_replaced}`
                    : 'first import'
                }
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-3 text-center">
              <CrossCheck
                label="Base (sale − buyer tax)"
                value={formatMoney(report.statement_base_amount)}
                sub={`${report.sales_count} orders`}
              />
              <CrossCheck
                label="Payouts to Payoneer"
                value={formatMoney(report.deposits_amount)}
                sub={`${report.deposits_count} deposits`}
              />
              <CrossCheck
                label="Refunds (not booked)"
                value={formatMoney(report.refunds_amount)}
                sub={`${report.refunds_count} rows`}
              />
            </div>

            {report.fee_overrides.length > 0 && (
              <ReportList
                tone="info"
                title={`${report.fee_overrides.length} fee${
                  report.fee_overrides.length === 1 ? '' : 's'
                } replaced by the statement`}
                hint="The statement is what Etsy actually charged, so it wins over a previously entered value."
                rows={report.fee_overrides.map((o) => ({
                  key: o.order_external_id,
                  left: o.order_external_id,
                  right: `${formatMoney(o.previous_platform_fee)} → ${formatMoney(
                    o.statement_platform_fee,
                  )}`,
                }))}
              />
            )}

            {report.credit_only_orders.length > 0 && (
              <ReportList
                tone="warn"
                title={`${report.credit_only_orders.length} credit-only order${
                  report.credit_only_orders.length === 1 ? '' : 's'
                }`}
                hint="Etsy refunded fees it charged in a period that has not been imported, so the fee is negative. Import the earlier month to resolve it."
                rows={report.credit_only_orders.map((o) => ({
                  key: o.order_external_id,
                  left: o.order_external_id,
                  right: formatMoney(o.platform_fee_amount),
                }))}
              />
            )}

            {report.unmatched_orders.length > 0 && (
              <ReportList
                tone="warn"
                title={`${report.unmatched_orders.length} order${
                  report.unmatched_orders.length === 1 ? '' : 's'
                } not in this shop`}
                hint="The lines are stored but linked to nothing — no order was created and no match was guessed. Import the matching order CSV, then re-run this statement."
                rows={report.unmatched_orders.map((o) => ({
                  key: o.order_external_id,
                  left: o.order_external_id,
                  right: formatMoney(o.platform_fee_amount),
                }))}
              />
            )}

            <div className="flex flex-col sm:flex-row gap-4 pt-2">
              <Button
                variant="ghost"
                className="px-8 h-12 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest"
                onClick={handleReset}
              >
                Import another month
              </Button>
              <Button
                className="px-8 h-12 bg-zinc-100 text-zinc-950 hover:bg-white rounded-xl font-bold uppercase text-[10px] tracking-widest"
                asChild
              >
                <a href="/orders">View orders</a>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <Card className="lg:col-span-2 border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl rounded-2xl overflow-hidden">
        <CardContent className="p-8 space-y-8">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-950 border border-zinc-800 text-teal-400 font-black text-xs shadow-inner">
              01
            </div>
            <h2 className="text-sm font-black uppercase tracking-widest text-zinc-100">
              Target shop
            </h2>
          </div>

          <p className="text-xs text-zinc-400 font-medium leading-relaxed">
            Pick the Etsy shop this statement belongs to. Order numbers are matched
            within that shop only.
          </p>

          <div className="space-y-4 pt-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 ml-1">
              Store identifier
            </p>
            <Select value={selectedShopId} onValueChange={setSelectedShopId}>
              <SelectTrigger className="w-full bg-zinc-950 border-zinc-800 h-12 rounded-xl">
                <SelectValue placeholder="Select shop" />
              </SelectTrigger>
              <SelectContent className="bg-zinc-950 border-zinc-800 rounded-xl">
                {shops.map((shop) => (
                  <SelectItem key={shop.id} value={shop.id} className="rounded-lg focus:bg-zinc-900">
                    <div className="flex items-center gap-3">
                      <div
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: shop.color || '#f59e0b' }}
                      />
                      <span className="text-sm font-semibold">{shop.name}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="rounded-xl border border-blue-500/10 bg-blue-500/5 p-5 flex gap-4">
            <Info className="h-5 w-5 text-blue-400 shrink-0" />
            <p className="text-[11px] text-blue-300/80 leading-relaxed font-medium">
              One calendar month per file. Re-importing a month replaces it, so
              running the same statement twice changes nothing.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card
        className={cn(
          'lg:col-span-3 border-zinc-800/60 transition-all duration-500 rounded-2xl overflow-hidden',
          selectedShopId
            ? 'bg-zinc-900/20 backdrop-blur-md opacity-100 shadow-2xl'
            : 'bg-zinc-900/5 opacity-40 grayscale blur-[1px] pointer-events-none',
        )}
      >
        <CardContent className="p-8 h-full flex flex-col">
          <div className="flex items-center gap-4 mb-10">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-zinc-950 border border-zinc-800 text-teal-400 font-black text-xs shadow-inner">
              02
            </div>
            <h2 className="text-sm font-black uppercase tracking-widest text-zinc-100">
              Statement file
            </h2>
          </div>

          <div
            className={cn(
              'flex-1 border-2 border-dashed rounded-3xl flex flex-col items-center justify-center p-10 transition-all gap-5',
              file
                ? 'border-teal-500/40 bg-teal-500/5'
                : 'border-zinc-800 bg-zinc-950 hover:border-teal-500/30 hover:bg-zinc-900/40 cursor-pointer',
            )}
            onClick={() => !file && fileInputRef.current?.click()}
          >
            <input
              type="file"
              className="hidden"
              accept=".csv"
              ref={fileInputRef}
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) setFile(e.target.files[0]);
              }}
            />

            <div
              className={cn(
                'h-20 w-20 rounded-2xl flex items-center justify-center mb-2 shadow-2xl transition-transform duration-500',
                file
                  ? 'bg-teal-500 shadow-teal-500/20 text-white scale-110'
                  : 'bg-zinc-900 border border-zinc-800 text-zinc-400',
              )}
            >
              {file ? <CheckCircle2 className="h-10 w-10" /> : <Receipt className="h-10 w-10" />}
            </div>

            <div className="text-center max-w-[240px]">
              <p className="text-sm font-black text-zinc-100 tracking-tight">
                {file ? file.name : 'Select payment statement'}
              </p>
              <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mt-2">
                {file ? `${(file.size / 1024).toFixed(1)} KB` : 'One month, CSV'}
              </p>
            </div>

            {file && (
              <Button
                variant="ghost"
                size="sm"
                className="text-[10px] font-black uppercase tracking-widest text-zinc-400 hover:text-red-400 hover:bg-red-400/5 rounded-lg"
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
              onClick={() => {
                if (!selectedShopId || !file) return;
                importMutation.mutate({ shopId: selectedShopId, file });
              }}
            >
              {importMutation.isPending ? 'Booking statement...' : 'Import statement'}
              {!importMutation.isPending && <Zap className="ml-3 h-4 w-4 fill-current" />}
            </Button>

            {importMutation.isError && (
              <div className="mt-4 p-4 rounded-xl border border-red-500/20 bg-red-500/5 flex gap-3 animate-in slide-in-from-top-1">
                <AlertCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p className="text-[11px] font-black text-red-400 uppercase tracking-widest">
                    Import rejected — nothing was written
                  </p>
                  {/* The backend aborts on the first row it cannot classify and
                      names it. Surfaced verbatim: it is the operator's fix. */}
                  <p className="text-[11px] text-red-300/80 font-medium leading-relaxed break-words">
                    {extractError(importMutation.error)}
                  </p>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: 'good' | 'warn';
}) {
  return (
    <div className="bg-zinc-950 border border-zinc-800 p-6 rounded-2xl">
      <p className="text-[10px] uppercase tracking-[0.15em] font-black text-zinc-600">{label}</p>
      <p
        className={cn(
          'text-2xl font-black tracking-tighter mt-3',
          tone === 'warn' ? 'text-amber-400' : 'text-teal-400',
        )}
      >
        {value}
      </p>
      {sub && <p className="text-[10px] font-bold text-zinc-500 mt-1.5">{sub}</p>}
    </div>
  );
}

function CrossCheck({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-2xl border border-zinc-800/60 bg-zinc-950/50 p-5">
      <p className="text-[10px] uppercase tracking-widest font-black text-zinc-600">{label}</p>
      <p className="text-lg font-black text-zinc-200 tracking-tight mt-2">{value}</p>
      <p className="text-[10px] font-bold text-zinc-600 mt-1">{sub}</p>
    </div>
  );
}

function ReportList({
  tone,
  title,
  hint,
  rows,
}: {
  tone: 'info' | 'warn';
  title: string;
  hint: string;
  rows: { key: string; left: string; right: string }[];
}) {
  return (
    <div
      className={cn(
        'rounded-2xl border p-6 text-left',
        tone === 'warn'
          ? 'border-amber-500/20 bg-amber-500/5'
          : 'border-zinc-800 bg-zinc-950/50',
      )}
    >
      <p
        className={cn(
          'text-[11px] font-black uppercase tracking-widest mb-2 flex items-center gap-2',
          tone === 'warn' ? 'text-amber-400' : 'text-zinc-300',
        )}
      >
        {tone === 'warn' ? <AlertTriangle size={14} /> : <Info size={14} />}
        {title}
      </p>
      <p className="text-[11px] text-zinc-500 font-medium leading-relaxed mb-4">{hint}</p>
      <div className="space-y-1.5 max-h-52 overflow-auto pr-3">
        {rows.map((row) => (
          <div
            key={row.key}
            className="flex items-center justify-between gap-4 text-[11px] py-1.5 border-b border-white/5 last:border-0"
          >
            <span className="font-mono text-zinc-400">{row.left}</span>
            <span className="font-bold text-zinc-300 tabular-nums">{row.right}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Pull the backend's `{"detail": "..."}` message out of an Axios error. */
function extractError(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;
  if (typeof detail === 'string') return detail;
  if (error instanceof Error) return error.message;
  return 'Unexpected error. Check the file is an Etsy payment statement export.';
}
