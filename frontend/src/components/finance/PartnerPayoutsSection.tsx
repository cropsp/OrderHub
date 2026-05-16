import { useMemo, useState } from 'react'
import { Calculator, Plus, Users } from 'lucide-react'

import { Button } from '@/components/ui/button'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import {
  useDeletePayment,
  useDeleteSettlement,
  usePartnerBalances,
  usePayments,
  useSettlements,
} from '@/hooks/usePartnerPayouts'
import type { PartnerPayment, PartnerSettlement } from '@/api/partnerPayouts'

import CalculateSettlementModal from './CalculateSettlementModal'
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
  const settlements = useSettlements(shopId)
  const payments = usePayments(shopId)
  const balances = usePartnerBalances(shopId)
  const deleteSettlement = useDeleteSettlement(shopId)
  const deletePayment = useDeletePayment(shopId)

  const [calcOpen, setCalcOpen] = useState(false)
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
          <p className="text-xs text-zinc-500">
            Settlements log, payments ledger, and per-partner balances.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            className="border-zinc-700 text-zinc-200 hover:bg-zinc-800"
            onClick={() => setCalcOpen(true)}
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
          onAction={() => setCalcOpen(true)}
        />
      ) : (
        <>
          {(balances.data?.items.length ?? 0) > 0 && (
            <PartnerBalancesSummary balances={balances.data?.items ?? []} />
          )}

          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              Settlements
            </p>
            <PartnerSettlementsTable
              items={settlements.data?.items ?? []}
              onRecordPayment={openRecordPayment}
              onDelete={handleDeleteSettlement}
            />
          </div>

          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
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

      <CalculateSettlementModal
        isOpen={calcOpen}
        onClose={() => setCalcOpen(false)}
        shopId={shopId}
        defaultPeriodStart={periodStart}
        defaultPeriodEnd={periodEnd}
      />
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
