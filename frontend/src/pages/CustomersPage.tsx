import { useEffect, useState } from 'react';
import { formatDate } from '@/lib/format';
import { Search, Users as UserGroup, Globe, ShoppingBag, Mail, History } from 'lucide-react';

import ShellPage from './ShellPage';
import { useCustomers } from '@/hooks/useCustomers';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { EmptyState } from '@/components/ui/EmptyState';
import { getInitials, getAvatarColor } from '@/utils/avatar';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';

const PAGE_LIMIT = 20;

export default function CustomersPage() {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      const next = searchInput.trim();
      setPage(1);
      setSearch(next);
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [searchInput]);

  const { data, isLoading, isFetching, error } = useCustomers({
    page,
    limit: PAGE_LIMIT,
    ...(search ? { search } : {}),
  });

  const items = data?.items ?? [];
  const canPrev = page > 1;
  const canNext = page < (data?.pages ?? 1);

  return (
    <ShellPage
      title="Customer directory"
      description="Intelligence and history for all platform customers."
    >
      <div className="space-y-6">
        {/* Search & Stats Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between bg-zinc-900/20 p-4 rounded-2xl border border-zinc-800/40">
          <div className="relative w-full max-w-md group">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-zinc-600 group-focus-within:text-teal-400 transition-colors" />
            <Input
              className="border-zinc-800 bg-zinc-950/50 pl-10 h-10 rounded-xl focus:ring-teal-500/20"
              placeholder="Search by name, email or country..."
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
          </div>
          
          <div className="flex items-center gap-6 px-2">
            <div className="flex flex-col items-end">
               <span className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">Total directory</span>
               <span className="text-sm font-bold text-zinc-200">
                  {isFetching && !isLoading ? (
                    <span className="animate-pulse">Updating...</span>
                  ) : (
                    `${data?.total ?? 0} Customers`
                  )}
               </span>
            </div>
          </div>
        </div>

        {error ? (
          <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-8 text-center text-red-400 font-medium">
            Failed to load customers. Please check your connection.
          </div>
        ) : (
          <Card className="overflow-hidden border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl rounded-2xl">
            <CardContent className="p-0">
              <Table>
                <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                  <TableRow className="border-none hover:bg-transparent">
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-6 py-4">Customer identity</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-4">Contact info</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-4">Geographic context</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 py-4 text-center">Volume</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 px-6 py-4 text-right">Relationship</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    [1, 2, 3, 4, 5, 6].map((i) => (
                      <TableRow key={i} className="border-zinc-800/40">
                        <TableCell colSpan={5} className="py-6 px-6">
                          <Skeleton className="h-8 w-full bg-zinc-900/40 rounded-lg" />
                        </TableCell>
                      </TableRow>
                    ))
                  ) : items.length === 0 ? (
                    <TableRow className="hover:bg-transparent border-none">
                      <TableCell colSpan={5} className="h-96">
                         <EmptyState 
                          icon={UserGroup} 
                          title="No customers found" 
                          description={search ? `We couldn't find any results matching "${search}"` : "Your customer directory is currently empty."}
                          actionLabel={search ? "Clear search" : undefined}
                          onAction={search ? () => setSearchInput('') : undefined}
                         />
                      </TableCell>
                    </TableRow>
                  ) : (
                    items.map((customer) => (
                      <TableRow key={customer.id} className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors group">
                        <TableCell className="px-6 py-5">
                          <div className="flex items-center gap-4">
                            <div className={cn(
                              "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-xs font-black text-white shadow-inner border border-white/10 transition-transform group-hover:scale-105",
                              getAvatarColor(customer.full_name)
                            )}>
                              {getInitials(customer.full_name)}
                            </div>
                            <div className="flex flex-col min-w-0">
                               <span className="text-sm font-bold text-zinc-100 tracking-tight truncate max-w-[200px]">
                                  {customer.full_name}
                               </span>
                               <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-tighter">
                                  UUID: {customer.id.slice(0, 8)}
                               </span>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="py-5">
                           <div className="flex items-center gap-2 text-zinc-400 group-hover:text-zinc-200 transition-colors">
                              <Mail size={12} className="text-zinc-600" />
                              <span className="text-xs font-medium">{customer.email}</span>
                           </div>
                        </TableCell>
                        <TableCell className="py-5">
                           <div className="flex items-center gap-2">
                              <Globe size={12} className="text-zinc-600" />
                              <Badge variant="outline" className="border-zinc-800 bg-zinc-900/50 text-zinc-400 font-mono text-[10px] tracking-widest py-0">
                                 {customer.country ? customer.country.toUpperCase() : 'Global'}
                              </Badge>
                           </div>
                        </TableCell>
                        <TableCell className="py-5 text-center">
                           <div className="inline-flex flex-col items-center gap-1">
                              <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-teal-500/5 border border-teal-500/10 text-teal-400">
                                 <ShoppingBag size={10} />
                                 <span className="text-xs font-black">{customer.order_count}</span>
                              </div>
                              <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-tighter">Total orders</span>
                           </div>
                        </TableCell>
                        <TableCell className="px-6 py-5 text-right">
                           <div className="flex flex-col items-end gap-1">
                              <div className="flex items-center gap-1.5 text-zinc-400">
                                 <History size={11} className="text-zinc-600" />
                                 <span className="text-xs font-semibold">{formatDate(customer.created_at)}</span>
                              </div>
                              <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-tighter italic">First seen</span>
                           </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Pagination Logic */}
        {!isLoading && !error && items.length > 0 && (
          <div className="flex items-center justify-between px-2">
            <p className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest">
              Directory page {data?.page ?? 1} of {data?.pages ?? 1}
            </p>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="h-9 px-4 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest transition-all"
                disabled={!canPrev}
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              >
                Previous
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-9 px-4 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest transition-all"
                disabled={!canNext}
                onClick={() => setPage((prev) => prev + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </ShellPage>
  );
}
