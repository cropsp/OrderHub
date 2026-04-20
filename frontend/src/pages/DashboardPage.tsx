import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useOrders } from '@/hooks/useOrders'
import { useShops } from '@/hooks/useShops'

import ShellPage from './ShellPage'

export default function DashboardPage() {
  const shopsQuery = useShops()
  const ordersQuery = useOrders({ page: 1, limit: 5 })

  const shopsCount = shopsQuery.data?.length ?? 0
  const ordersCount = ordersQuery.data?.total ?? 0
  const statusLabel = shopsQuery.isLoading || ordersQuery.isLoading ? 'Syncing' : 'Online'

  return (
    <ShellPage
      description="Core shell is connected. Protected routes and data hooks are active."
      title="Dashboard"
    >
      <section className="grid gap-4 md:grid-cols-3">
        <Card className="border border-slate-800/90 bg-slate-900/70">
          <CardHeader>
            <CardTitle>Backend Status</CardTitle>
            <CardDescription>Auth + API hooks are connected.</CardDescription>
          </CardHeader>
          <CardContent className="text-2xl font-semibold text-teal-300">{statusLabel}</CardContent>
        </Card>

        <Card className="border border-slate-800/90 bg-slate-900/70">
          <CardHeader>
            <CardTitle>Active Shops</CardTitle>
            <CardDescription>Loaded from `/api/shops`.</CardDescription>
          </CardHeader>
          <CardContent className="text-2xl font-semibold text-sky-300">{shopsCount}</CardContent>
        </Card>

        <Card className="border border-slate-800/90 bg-slate-900/70">
          <CardHeader>
            <CardTitle>Total Orders</CardTitle>
            <CardDescription>Loaded from `/api/orders`.</CardDescription>
          </CardHeader>
          <CardContent className="text-2xl font-semibold text-amber-300">{ordersCount}</CardContent>
        </Card>
      </section>
    </ShellPage>
  )
}
