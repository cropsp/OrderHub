import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { Search } from 'lucide-react';

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
      title="Customers"
      description="Customer directory with historical order counts."
    >
      <div className="space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full max-w-md">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -tranzinc-y-1/2 text-zinc-500" />
            <Input
              className="border-zinc-700 bg-zinc-900/50 pl-8"
              placeholder="Search by customer name or email..."
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
          </div>
          <p className="text-xs text-zinc-500">
            {isFetching && !isLoading ? 'Updating...' : `${data?.total ?? 0} customers`}
          </p>
        </div>

        {error ? (
          <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-8 text-center text-red-400">
            Failed to load customers. Please try again.
          </div>
        ) : (
          <Card className="overflow-hidden border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm shadow-md">
            <CardContent className="p-0">
              <Table>
                <TableHeader className="bg-zinc-800/30">
                  <TableRow className="border-zinc-800/60 hover:bg-transparent">
                    <TableHead className="text-zinc-400">Customer</TableHead>
                    <TableHead className="text-zinc-400">Email</TableHead>
                    <TableHead className="text-zinc-400">Country</TableHead>
                    <TableHead className="text-zinc-400">Orders</TableHead>
                    <TableHead className="text-zinc-400">Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    [1, 2, 3, 4, 5, 6].map((i) => (
                      <TableRow key={i} className="border-zinc-800/60">
                        <TableCell colSpan={5}>
                          <Skeleton className="h-8 w-full bg-zinc-900/60" />
                        </TableCell>
                      </TableRow>
                    ))
                  ) : items.length === 0 ? (
                    <TableRow className="border-zinc-800/60">
                      <TableCell className="h-24 text-center text-zinc-500" colSpan={5}>
                        No customers found.
                      </TableCell>
                    </TableRow>
                  ) : (
                    items.map((customer) => (
                      <TableRow key={customer.id} className="border-zinc-800/60 hover:bg-zinc-800/20">
                        <TableCell className="font-medium text-zinc-200">{customer.full_name}</TableCell>
                        <TableCell className="text-zinc-300">{customer.email}</TableCell>
                        <TableCell className="text-zinc-400">
                          {customer.country ? customer.country.toUpperCase() : 'N/A'}
                        </TableCell>
                        <TableCell className="text-zinc-200">{customer.order_count}</TableCell>
                        <TableCell className="text-zinc-400">
                          {format(new Date(customer.created_at), 'MMM dd, yyyy')}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {!isLoading && !error && (
          <div className="flex items-center justify-between">
            <p className="text-xs text-zinc-500">
              Page {data?.page ?? 1} of {data?.pages ?? 1}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
                disabled={!canPrev}
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                className="border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
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
