import { useState, type FormEvent } from 'react';
import { format } from 'date-fns';
import { 
  UserPlus, 
  Shield, 
  UserX, 
  UserCheck, 
  Mail, 
  MoreVertical,
  Users as UserGroup,
  Clock
} from 'lucide-react';
import { useCreateUser, useUsers, useUpdateUser } from '@/hooks/useUsers';
import { useAuth } from '@/hooks/useAuth';
import type { UserRoleType } from '@/types/user';
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
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { EmptyState } from '@/components/ui/EmptyState';
import { getInitials, getAvatarColor } from '@/utils/avatar';
import { cn } from '@/lib/utils';
import type { User } from '@/types/user';

const ROLE_COLORS = {
  owner: 'bg-teal-500/10 text-teal-400 border-teal-500/20',
  manager: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
  designer: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
};

function getErrorMessage(error: unknown) {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    // TODO: SEC-07 — backend now returns generic detail; reconsider message extraction.
    return response?.data?.detail ?? 'Request failed';
  }

  if (error instanceof Error) return error.message;
  return 'Request failed';
}

function getTemporaryPassword(response: unknown): string | null {
  if (!response || typeof response !== 'object') return null;
  const payload = response as { temporary_password?: unknown };
  return typeof payload.temporary_password === 'string' ? payload.temporary_password : null;
}

export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const { data: users, isLoading } = useUsers();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [newUser, setNewUser] = useState({
    full_name: '',
    email: '',
    role: 'designer' as UserRoleType,
  });
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editRole, setEditRole] = useState<UserRoleType>('designer');
  const [editIsActive, setEditIsActive] = useState(true);
  const [editError, setEditError] = useState<string | null>(null);
  
  const isOwner = currentUser?.role === 'owner';

  const toggleUserStatus = (userId: string, currentStatus: boolean) => {
    updateUser.mutate({ id: userId, payload: { is_active: !currentStatus } });
  };

  const resetCreateForm = () => {
    setCreateError(null);
    setTemporaryPassword(null);
    setNewUser({
      full_name: '',
      email: '',
      role: 'designer',
    });
  };

  const handleCreateUser = async (event: FormEvent) => {
    event.preventDefault();
    setCreateError(null);

    if (!newUser.full_name.trim() || !newUser.email.trim()) {
      setCreateError('Full name and email are required.');
      return;
    }

    try {
      const created = await createUser.mutateAsync({
        full_name: newUser.full_name.trim(),
        email: newUser.email.trim(),
        role: newUser.role,
      });
      setTemporaryPassword(getTemporaryPassword(created));
      setNewUser({
        full_name: '',
        email: '',
        role: 'designer',
      });
    } catch (createErr) {
      setCreateError(getErrorMessage(createErr));
    }
  };

  const openEditPermissions = (userToEdit: User) => {
    setEditingUser(userToEdit);
    setEditRole(userToEdit.role);
    setEditIsActive(userToEdit.is_active);
    setEditError(null);
  };

  const handleUpdatePermissions = async (event: FormEvent) => {
    event.preventDefault();
    if (!editingUser) return;

    setEditError(null);
    try {
      await updateUser.mutateAsync({
        id: editingUser.id,
        payload: {
          role: editRole,
          is_active: editIsActive,
        },
      });
      setEditingUser(null);
    } catch (updateErr) {
      setEditError(getErrorMessage(updateErr));
    }
  };

  return (
    <ShellPage
      title="Team intelligence"
      description="Manage access control and operational roles for your organization."
    >
      <Dialog
        open={isCreateOpen}
        onOpenChange={(open) => {
          setIsCreateOpen(open);
          if (!open) resetCreateForm();
        }}
      >
        <DialogContent className="max-w-md border-zinc-800 bg-zinc-950 text-zinc-100 rounded-2xl overflow-hidden shadow-[0_0_50px_-12px_rgba(0,0,0,0.5)]">
          <DialogHeader className="p-1 px-1">
            <DialogTitle className="text-xl font-bold tracking-tight">Add Team Member</DialogTitle>
            <DialogDescription className="text-xs text-zinc-500 font-medium">
              Initialize a new user account and assign structural permissions.
            </DialogDescription>
          </DialogHeader>

          <form className="space-y-6 pt-2" onSubmit={handleCreateUser}>
            <div className="space-y-4">
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 ml-1">Identity Name</p>
                <Input
                  className="border-zinc-800 bg-zinc-900/50 h-11 rounded-xl focus:ring-teal-500/20"
                  placeholder="e.g. Alex Johnson"
                  value={newUser.full_name}
                  onChange={(event) => setNewUser((prev) => ({ ...prev, full_name: event.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 ml-1">Work Email</p>
                <Input
                  className="border-zinc-800 bg-zinc-900/50 h-11 rounded-xl focus:ring-teal-500/20"
                  placeholder="member@orderhub.dev"
                  type="email"
                  value={newUser.email}
                  onChange={(event) => setNewUser((prev) => ({ ...prev, email: event.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 ml-1">System Role</p>
                <Select
                  value={newUser.role}
                  onValueChange={(value) => setNewUser((prev) => ({ ...prev, role: value as UserRoleType }))}
                >
                  <SelectTrigger className="w-full border-zinc-800 bg-zinc-900/50 h-11 rounded-xl">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-zinc-800 bg-zinc-900 rounded-xl">
                    <SelectItem value="owner">OWNER (FULL ACCESS)</SelectItem>
                    <SelectItem value="manager">MANAGER (OPERATIONS)</SelectItem>
                    <SelectItem value="designer">DESIGNER (PRODUCTION)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {temporaryPassword && (
              <div className="rounded-xl border border-teal-500/20 bg-teal-500/5 p-4 animate-in zoom-in-95 duration-300">
                <div className="flex items-center gap-2 mb-2">
                   <div className="size-2 rounded-full bg-teal-500 animate-pulse" />
                   <p className="text-[10px] font-black uppercase tracking-widest text-teal-400">
                    One-Time Password Generated
                  </p>
                </div>
                <div className="bg-zinc-950 border border-teal-500/10 rounded-lg p-3 font-mono text-sm text-teal-100 text-center select-all cursor-copy">
                  {temporaryPassword}
                </div>
                <p className="mt-3 text-[10px] text-zinc-500 text-center italic">
                  Note: This credential will never be shown again.
                </p>
              </div>
            )}

            {createError && (
              <p className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-[11px] font-medium text-red-400 text-center">
                {createError}
              </p>
            )}

            <DialogFooter className="bg-zinc-900/30 -mx-6 -mb-6 p-6 mt-8 flex flex-row gap-3">
              <Button
                type="button"
                variant="ghost"
                className="flex-1 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest h-11 transition-all"
                onClick={() => setIsCreateOpen(false)}
              >
                Dismiss
              </Button>
              <Button
                type="submit"
                className="flex-1 bg-teal-600 text-white hover:bg-teal-500 rounded-xl font-bold uppercase text-[10px] tracking-widest h-11 transition-all shadow-lg shadow-teal-900/20"
                disabled={createUser.isPending}
              >
                {createUser.isPending ? 'Processing...' : 'Deploy Member'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(editingUser)}
        onOpenChange={(open) => {
          if (!open) {
            setEditingUser(null);
            setEditError(null);
          }
        }}
      >
        <DialogContent className="max-w-md border-zinc-800 bg-zinc-950 text-zinc-100 rounded-2xl overflow-hidden shadow-[0_0_50px_-12px_rgba(0,0,0,0.5)]">
          <DialogHeader className="p-1 px-1">
            <DialogTitle className="text-xl font-bold tracking-tight">Modify Permissions</DialogTitle>
            <DialogDescription className="text-xs text-zinc-500 font-medium">
              Update roles and status for {editingUser?.full_name}.
            </DialogDescription>
          </DialogHeader>

          <form className="space-y-6 pt-2" onSubmit={handleUpdatePermissions}>
            <div className="space-y-4">
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 ml-1">Structural Role</p>
                <Select value={editRole} onValueChange={(value) => setEditRole(value as UserRoleType)}>
                  <SelectTrigger className="w-full border-zinc-800 bg-zinc-900/50 h-11 rounded-xl">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-zinc-800 bg-zinc-900 rounded-xl">
                    <SelectItem value="owner">OWNER</SelectItem>
                    <SelectItem value="manager">MANAGER</SelectItem>
                    <SelectItem value="designer">DESIGNER</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 ml-1">Lifecycle Status</p>
                <Select
                  value={editIsActive ? 'active' : 'inactive'}
                  onValueChange={(value) => setEditIsActive(value === 'active')}
                >
                  <SelectTrigger className="w-full border-zinc-800 bg-zinc-900/50 h-11 rounded-xl">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-zinc-800 bg-zinc-900 rounded-xl">
                    <SelectItem value="active">Active (Access Granted)</SelectItem>
                    <SelectItem value="inactive">Inactive (Revoked)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {editError && (
              <p className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-[11px] font-medium text-red-400 text-center">
                {editError}
              </p>
            )}

            <DialogFooter className="bg-zinc-900/30 -mx-6 -mb-6 p-6 mt-8 flex flex-row gap-3">
              <Button
                type="button"
                variant="ghost"
                className="flex-1 border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-xl font-bold uppercase text-[10px] tracking-widest h-11 transition-all"
                onClick={() => setEditingUser(null)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                className="flex-1 bg-sky-600 text-white hover:bg-sky-500 rounded-xl font-bold uppercase text-[10px] tracking-widest h-11 transition-all shadow-lg shadow-sky-900/20"
                disabled={updateUser.isPending}
              >
                {updateUser.isPending ? 'Syncing...' : 'Save Changes'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <div className="space-y-6">
        {/* Modern Header Section */}
        <div className="flex items-center justify-between bg-zinc-900/20 p-4 rounded-2xl border border-zinc-800/40">
          <div className="flex items-center gap-3">
             <div className="size-10 rounded-xl bg-zinc-950 border border-zinc-800 flex items-center justify-center shadow-inner">
                <UserGroup className="size-5 text-zinc-500" />
             </div>
             <div>
                <h2 className="text-sm font-bold text-zinc-100 tracking-tight">Active Team</h2>
                <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                  {isLoading ? 'Scanning...' : `${users?.length ?? 0} Accounts Registered`}
                </p>
             </div>
          </div>
          {isOwner && (
            <Button
              className="bg-teal-600 hover:bg-teal-500 text-white rounded-xl font-bold uppercase text-[10px] tracking-widest h-10 px-5 shadow-lg shadow-teal-900/20 transition-all"
              onClick={() => setIsCreateOpen(true)}
            >
              <UserPlus className="mr-2 h-4 w-4" /> Add Member
            </Button>
          )}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20 w-full bg-zinc-900/40 rounded-2xl" />
            ))}
          </div>
        ) : users?.length === 0 ? (
           <Card className="border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md rounded-2xl">
              <CardContent className="p-0">
                 <EmptyState 
                    icon={UserGroup} 
                    title="No users found" 
                    description="Your team directory is empty. Add your first member to begin collaborating."
                 />
              </CardContent>
           </Card>
        ) : (
          <Card className="overflow-hidden border-zinc-800/60 bg-zinc-900/20 backdrop-blur-md shadow-2xl rounded-2xl">
            <CardContent className="p-0">
              <Table>
                <TableHeader className="bg-white/[0.02] border-b border-white/[0.03]">
                  <TableRow className="border-none hover:bg-transparent">
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-6 py-4">User identity</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">Role & Access</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">Current Status</TableHead>
                    <TableHead className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 py-4">Engagement</TableHead>
                    {isOwner && <TableHead className="text-right text-[10px] font-bold uppercase tracking-widest text-zinc-500 px-6 py-4">Control</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users?.map((u) => (
                    <TableRow key={u.id} className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors group">
                      <TableCell className="px-6 py-5">
                        <div className="flex items-center gap-4">
                          <div className={cn(
                            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-xs font-black text-white shadow-inner border border-white/10 transition-transform group-hover:scale-105",
                            getAvatarColor(u.full_name)
                          )}>
                            {getInitials(u.full_name)}
                          </div>
                          <div className="flex flex-col min-w-0">
                             <span className="text-sm font-bold text-zinc-100 tracking-tight">
                                {u.full_name} {u.id === currentUser?.id && <span className="text-[10px] text-zinc-500 italic ml-1 font-normal">(You)</span>}
                             </span>
                             <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 font-medium">
                                <Mail size={10} className="text-zinc-700" />
                                {u.email}
                             </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="py-5">
                        <Badge variant="outline" className={cn("px-2 py-0.5 rounded-lg border font-mono text-[9px] tracking-widest uppercase", ROLE_COLORS[u.role as keyof typeof ROLE_COLORS])}>
                          <Shield className="mr-1.5 h-3 w-3" />
                          {u.role}
                        </Badge>
                      </TableCell>
                      <TableCell className="py-5">
                        {u.is_active ? (
                          <div className="inline-flex items-center gap-2 px-2 py-0.5 rounded-full bg-teal-500/5 text-teal-400 border border-teal-500/10 text-[10px] font-bold tracking-tight">
                            <UserCheck className="h-3.5 w-3.5" />
                            Active Member
                          </div>
                        ) : (
                          <div className="inline-flex items-center gap-2 px-2 py-0.5 rounded-full bg-zinc-900 text-zinc-500 border border-zinc-800 text-[10px] font-bold tracking-tight">
                            <UserX className="h-3.5 w-3.5" />
                            Access Revoked
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="py-5">
                        <div className="flex items-center gap-1.5 text-zinc-400">
                           <Clock size={11} className="text-zinc-600" />
                           <span className="text-[11px] font-semibold tracking-tight">
                              Joined {format(new Date(u.created_at), 'MMM yyyy')}
                           </span>
                        </div>
                      </TableCell>
                      {isOwner && u.id !== currentUser?.id && (
                        <TableCell className="px-6 py-5 text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon-sm" className="size-8 rounded-lg text-zinc-500 hover:text-zinc-100 hover:bg-zinc-800 transition-all">
                                <MoreVertical className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-56 bg-zinc-950 border-zinc-800 rounded-xl p-1 shadow-2xl">
                              <DropdownMenuItem
                                className="text-[11px] font-bold uppercase tracking-wider text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 rounded-lg cursor-pointer px-3 py-2.5"
                                onClick={() => openEditPermissions(u)}
                              >
                                Modify Permissions
                              </DropdownMenuItem>
                              <DropdownMenuItem 
                                className={cn(
                                  "text-[11px] font-bold uppercase tracking-wider rounded-lg cursor-pointer px-3 py-2.5 mt-0.5",
                                  u.is_active ? 'text-red-400 hover:bg-red-500/10' : 'text-teal-400 hover:bg-teal-500/10'
                                )}
                                onClick={() => toggleUserStatus(u.id, u.is_active)}
                              >
                                {u.is_active ? 'Revoke System Access' : 'Restore System Access'}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      )}
                      {u.id === currentUser?.id && isOwner && (
                        <TableCell className="px-6 py-5 text-right">
                           <div className="size-8 ml-auto flex items-center justify-center rounded-lg bg-zinc-900/50 border border-zinc-800">
                              <Shield className="size-4 text-teal-500/40" />
                           </div>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </div>
    </ShellPage>
  );
}
