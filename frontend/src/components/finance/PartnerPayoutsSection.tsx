import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Calculator, Plus, Users } from 'lucide-react'

import { Button } from '@/components/ui/button'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import {
  useCheckStaleness,
  useDeletePayment,
  useDeleteSettlement,
  usePartnerBalances,
  usePayments,
  useSettlements,
} from '@/hooks/usePartnerPayouts'
import { useToastStore } from '@/components/ui/Toast'
import type { SettlementStaleness } from '@/types/partner'
import type { PartnerPayment, PartnerSettlement } from '@/api/partnerPayouts'

import PartnerBalancesSummary from './PartnerBalancesSummary'
import PartnerPaymentsTable from './PartnerPaymentsTable'
import PartnerSettlementsTable from './PartnerSettlementsTable'
import RecordPaymentModal from './RecordPaymentModal'

type PendingConfirm =
  | { kind: 'settlement'; target: PartnerSettlement }
  | { kind: 'payment'; target: PartnerPayment }

interface PartnerPayoutsSectionProps {
  shopId: string
  periodStart: string
  periodEnd: string
}

export default function PartnerPayoutsSection({
  shopId,
  periodStart,
  periodEnd,
}: PartnerPayoutsSectionProps) {
  const navigate = useNavigate()
  const settlements = useSettlements(shopId)
  const payments = usePayments(shopId)
  const balances = usePartnerBalances(shopId)
  const deleteSettlement = useDeleteSettlement(shopId)
  const deletePayment = useDeletePayment(shopId)
  const checkStaleness = useCheckStaleness(shopId)
  const addToast = useToastStore(s => s.addToast)

  // Transient by design: a settlement is immutable, so a staleness verdict is
  // never persisted. It is recomputed on demand and lives only in this state.
  const [staleness, setStaleness] = useState<Record<string, SettlementStaleness>>(
    {},
  )

  const handleCheckStaleness = async () => {
    const result = await checkStaleness.mutateAsync(undefined)
    setStaleness(
      Object.fromEntries(result.items.map(i => [i.settlement_id, i])),
    )
    const staleCount = result.items.filter(i => i.stale).length
    addToast(
      staleCount === 0
        ? `Checked ${result.checked_count} open settlement(s) — all still current.`
        : `${staleCount} of ${result.checked_count} open settlement(s) have moved. Delete and recalculate to correct.`,
      staleCount === 0 ? 'success' : 'info',
    )
  }

  const [paymentOpen, setPaymentOpen] = useState(false)
  const [paymentPrefill, setPaymentPrefill] = useState<PartnerSettlement | null>(
    null,
  )
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(
    null,
  )

  const settlementsById = useMemo(() => {
    const out: Record<string, PartnerSettlement> = {}
    for (const s of settlements.data?.items ?? []) out[s.id] = s
    return out
  }, [settlements.data])

  const isEmpty =
    !settlements.isLoading &&
    !payments.isLoading &&
    (settlements.data?.items.length ?? 0) === 0 &&
    (payments.data?.items.length ?? 0) === 0

  const openCalculate = () => {
    navigate(
      `/shops/${shopId}/finance/settlement?start=${periodStart}&end=${periodEnd}`,
    )
  }

  const openRecordPayment = (s?: PartnerSettlement) => {
    setPaymentPrefill(s ?? null)
    setPaymentOpen(true)
  }

  const handleDeleteSettlement = (s: PartnerSettlement) => {
    setPendingConfirm({ kind: 'settlement', target: s })
  }

  const isMutatingConfirm =
    deleteSettlement.isPending || deletePayment.isPending

  const confirmBody = (() => {
    if (!pendingConfirm) return ''
    if (pendingConfirm.kind === 'settlement') {
      const s = pendingConfirm.target
      const paid = Number(s.paid_amount)
      return paid > 0
        ? `This settlement has linked payments totaling ${paid.toFixed(
            2,
          )} ${s.base_currency}. Those payments will remain in the ledger but become unlinked. Delete settlement?`
        : 'Delete this settlement?'
    }
    const p = pendingConfirm.target
    return `Delete payment of ${Number(p.amount).toFixed(2)} ${p.currency}?`
  })()

  const confirmTitle =
    pendingConfirm?.kind === 'payment' ? 'Delete payment?' : 'Delete settlement?'

  const handleConfirmDelete = async () => {
    if (!pendingConfirm) return
    if (pendingConfirm.kind === 'settlement') {
      await deleteSettlement.mutateAsync(pendingConfirm.target.id)
    } else {
      await deletePayment.mutateAsync(pendingConfirm.target.id)
    }
    setPendingConfirm(null)
  }

  return (
    <div className="rounded-3xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold tracking-tight text-zinc-100">
            Partner Payouts
          </h2>
          <p className="text-xs text-zinc-400">
            Settlements log, payments ledger, and per-partner balances.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="border-zinc-700 text-zinc-200 hover:bg-zinc-800"
            onClick={openCalculate}
          >
            <Calculator className="size-3.5" />
            Calculate Settlement
          </Button>
          <Button
            size="sm"
            className="bg-emerald-600 hover:bg-emerald-500 text-white"
            onClick={() => openRecordPayment()}
          >
            <Plus className="size-3.5" />
            Record Payment
          </Button>
        </div>
      </div>

      {isEmpty ? (
        <EmptyState
          icon={Users}
          title="No partner activity yet"
          description="Calculate a settlement to start tracking partner shares for this shop."
          actionLabel="Calculate Settlement"
          onAction={openCalculate}
        />
      ) : (
        <>
          {(balances.data?.items.length ?? 0) > 0 && (
            <PartnerBalancesSummary balances={balances.data?.items ?? []} />
          )}

          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
              Settlements
            </p>
            <PartnerSettlementsTable
              staleness={staleness}
              onCheckStaleness={handleCheckStaleness}
              isCheckingStaleness={checkStaleness.isPending}
              items={settlements.data?.items ?? []}
              onRecordPayment={openRecordPayment}
              onDelete={handleDeleteSettlement}
            />
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
              Payments
            </p>
            <PartnerPaymentsTable
              items={payments.data?.items ?? []}
              settlementsById={settlementsById}
              onDelete={(p) =>
                setPendingConfirm({ kind: 'payment', target: p })
              }
            />
          </div>
        </>
      )}

      <RecordPaymentModal
        isOpen={paymentOpen}
        onClose={() => setPaymentOpen(false)}
        shopId={shopId}
        prefillSettlement={paymentPrefill}
      />
      <ConfirmDialog
        isOpen={pendingConfirm !== null}
        onClose={() => {
          if (!isMutatingConfirm) setPendingConfirm(null)
        }}
        title={confirmTitle}
        body={confirmBody}
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={handleConfirmDelete}
        isLoading={isMutatingConfirm}
      />
    </div>
  )
}
