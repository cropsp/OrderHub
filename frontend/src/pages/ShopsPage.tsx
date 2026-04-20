import { 
  Plus, 
  Settings2, 
  Trash2, 
  CheckCircle2, 
  AlertCircle,
  RefreshCw
} from 'lucide-react';
import { useShops, useDeleteShop, useSyncShop } from '@/hooks/useShops';
import ShellPage from './ShellPage';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent } from '@/components/ui/card';
import { useAuth } from '@/hooks/useAuth';
import { cn } from '@/lib/utils';

export default function ShopsPage() {
  const { user } = useAuth();
  const { data: shops, isLoading, error } = useShops();
  const deleteShop = useDeleteShop();
  const syncShop = useSyncShop();
  
  const isOwner = user?.role === 'owner';

  if (error) {
    return (
      <ShellPage title="Shop Management" description="Error loading shops.">
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-8 text-center text-red-400">
          Failed to load shops. Please check your connection.
        </div>
      </ShellPage>
    );
  }

  return (
    <ShellPage
      title="Shop Management"
      description="Connect and manage your Etsy and Shopify stores."
    >
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-200">Integrated Stores</h2>
          {isOwner && (
            <Button className="bg-teal-600 hover:bg-teal-500 text-white">
              <Plus className="mr-2 h-4 w-4" /> Add Store
            </Button>
          )}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16 w-full bg-slate-900/60" />
            ))}
          </div>
        ) : (
          <Card className="border-slate-800/60 bg-slate-900/40 backdrop-blur-sm shadow-md overflow-hidden">
            <CardContent className="p-0">
              <Table>
                <TableHeader className="bg-slate-800/30">
                  <TableRow className="border-slate-800/60 hover:bg-transparent">
                    <TableHead className="w-[300px] text-slate-400">Store Name</TableHead>
                    <TableHead className="text-slate-400">Platform</TableHead>
                    <TableHead className="text-slate-400">Status</TableHead>
                    <TableHead className="text-slate-400">API Connection</TableHead>
                    {isOwner && <TableHead className="text-right text-slate-400">Actions</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Array.isArray(shops) && shops.map((shop) => (
                    <TableRow key={shop.id} className="border-slate-800/60 hover:bg-slate-800/20">
                      <TableCell className="font-medium text-slate-200">
                        <div className="flex items-center gap-3">
                          <div 
                            className="h-3 w-3 rounded-full" 
                            style={{ backgroundColor: shop.color || '#94a3b8' }} 
                          />
                          {shop.name}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="border-slate-700 bg-slate-800/50 text-slate-300">
                          {String(shop.platform || '').toUpperCase()}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2 text-xs text-teal-400">
                          <CheckCircle2 className="h-3 w-3" />
                          Active
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          {shop.has_shopify_token || shop.has_np_token ? (
                            <Badge className="bg-teal-500/10 text-teal-400 border-teal-500/30">Connected</Badge>
                          ) : (
                            <Badge className="bg-slate-500/10 text-slate-500 border-slate-500/30">Manual Only</Badge>
                          )}
                        </div>
                      </TableCell>
                      {isOwner && (
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-2 text-right">
                            {shop.platform?.toLowerCase() === 'shopify' && (
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className={cn(
                                  "h-8 w-8 text-teal-500 hover:text-teal-400 hover:bg-teal-500/10",
                                  syncShop.isPending && "animate-spin"
                                )}
                                disabled={syncShop.isPending}
                                onClick={() => syncShop.mutate(shop.id)}
                              >
                                <RefreshCw className="h-4 w-4" />
                              </Button>
                            )}
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-slate-100">
                              <Settings2 className="h-4 w-4" />
                            </Button>
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="h-8 w-8 text-slate-400 hover:text-red-400"
                              onClick={() => {
                                if (window.confirm(`Are you sure you want to deactivate ${shop.name}?`)) {
                                  deleteShop.mutate(shop.id);
                                }
                              }}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                  {(!shops || (Array.isArray(shops) && shops.length === 0)) && (
                    <TableRow>
                      <TableCell colSpan={5} className="h-24 text-center text-slate-500">
                        No stores connected yet.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
          <div className="flex gap-3">
            <AlertCircle className="h-5 w-5 text-amber-400 shrink-0" />
            <div className="space-y-1">
              <h4 className="text-sm font-medium text-amber-400">Technical Note</h4>
              <p className="text-xs text-amber-500/80 leading-relaxed">
                Tokens and API keys are stored with industry-standard encryption on the server. 
                Managers and Designers cannot view or modify these credentials.
              </p>
            </div>
          </div>
        </div>
      </div>
    </ShellPage>
  );
}
