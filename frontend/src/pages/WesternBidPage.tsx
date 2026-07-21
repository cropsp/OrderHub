import { useState } from 'react'
import { Truck } from 'lucide-react'

import { formatDateTime } from '@/lib/format'
import { useWbParcels } from '@/hooks/useWesternBid'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import ShellPage from './ShellPage'

const EM_DASH = '—'

/**
 * WB-1 read-only mirror of WesternBid sent parcels, newest first. Raw status
 * fields, no actions — matching / labels land in WB-2 / WB-3. Until the API key
 * arrives (ticket-gated) the table is legitimately empty.
 */
export default function WesternBidPage() {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useWbParcels({ page, limit: 50 })

  const parcels = data?.items ?? []
  const totalPages = data?.pages ?? 0

  return (
    <ShellPage
      title="WesternBid Parcels"
      description="Read-only mirror of parcels sent via WesternBid. Synced every 15 minutes."
    >
      <Card className="border-zinc-800/60 bg-zinc-900/40 backdrop-blur-sm">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-800 hover:bg-transparent">
                <TableHead className="text-zinc-400">Recipient</TableHead>
                <TableHead className="text-zinc-400">Country</TableHead>
                <TableHead className="text-zinc-400">Carrier</TableHead>
                <TableHead className="text-zinc-400">Shipping Type</TableHead>
                <TableHead className="text-zinc-400">Tracking</TableHead>
                <TableHead className="text-zinc-400">Status</TableHead>
                <TableHead className="text-zinc-400">Payment</TableHead>
                <TableHead className="text-zinc-400">Created</TableHead>
                <TableHead className="text-zinc-400">Last Seen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i} className="border-zinc-800">
                    {Array.from({ length: 9 }).map((__, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-5 w-20 bg-zinc-800" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : parcels.length === 0 ? (
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableCell colSpan={9} className="py-16 text-center">
                    <div className="flex flex-col items-center gap-2 text-zinc-500">
                      <Truck className="h-8 w-8 opacity-50" />
                      <p className="text-sm">No WesternBid parcels mirrored yet.</p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                parcels.map((p) => (
                  <TableRow key={p.shipment_id} className="border-zinc-800">
                    <TableCell className="text-zinc-200">
                      {p.recipient_name ?? EM_DASH}
                    </TableCell>
                    <TableCell className="text-zinc-300">
                      {p.recipient_country_code ?? EM_DASH}
                    </TableCell>
                    <TableCell className="text-zinc-300">
                      {p.carrier_type ?? EM_DASH}
                    </TableCell>
                    <TableCell className="text-zinc-300">
                      {p.shipping_type ?? EM_DASH}
                    </TableCell>
                    <TableCell className="text-zinc-300">
                      {p.tracking_numbers.length > 0
                        ? p.tracking_numbers.join(', ')
                        : EM_DASH}
                    </TableCell>
                    <TableCell>
                      {p.wb_status ? (
                        <Badge
                          variant="outline"
                          className="border-zinc-700 bg-zinc-800/40 text-zinc-200"
                        >
                          {p.wb_status}
                        </Badge>
                      ) : (
                        EM_DASH
                      )}
                    </TableCell>
                    <TableCell className="text-zinc-300">
                      {p.payment_status ?? EM_DASH}
                    </TableCell>
                    <TableCell className="text-zinc-400">
                      {formatDateTime(p.wb_created_at)}
                    </TableCell>
                    <TableCell className="text-zinc-400">
                      {formatDateTime(p.last_seen_at)}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-end gap-3 text-sm text-zinc-400">
          <span>
            Page {data?.page ?? page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </ShellPage>
  )
}
