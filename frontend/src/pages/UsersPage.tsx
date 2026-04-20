import { useState, type FormEvent } from 'react';
import { 
  UserPlus, 
  Shield, 
  UserX, 
  UserCheck, 
  Mail, 
  MoreVertical 
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
import type { User } from '@/types/user';

const ROLE_COLORS = {
  owner: 'bg-teal-500/10 text-teal-400 border-teal-500/30',
  manager: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
  designer: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30',
};

function getErrorMessage(error: unknown) {
  if (error && typeof error === 'object' && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
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
      title="User Management"
      description="Manage team access and role-based permissions."
    >
      <Dialog
        open={isCreateOpen}
        onOpenChange={(open) => {
          setIsCreateOpen(open);
          if (!open) resetCreateForm();
        }}
      >
        <DialogContent className="max-w-md border-slate-800 bg-slate-950 text-slate-100">
          <DialogHeader>
            <DialogTitle>Add Team Member</DialogTitle>
            <DialogDescription className="text-slate-400">
              Create a user account and assign an initial role.
            </DialogDescription>
          </DialogHeader>

          <form className="space-y-4" onSubmit={handleCreateUser}>
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Full Name</p>
              <Input
                className="border-slate-700 bg-slate-900/50"
                placeholder="Team member name"
                value={newUser.full_name}
                onChange={(event) => setNewUser((prev) => ({ ...prev, full_name: event.target.value }))}
              />
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Email</p>
              <Input
                className="border-slate-700 bg-slate-900/50"
                placeholder="member@orderhub.dev"
                type="email"
                value={newUser.email}
                onChange={(event) => setNewUser((prev) => ({ ...prev, email: event.target.value }))}
              />
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Role</p>
              <Select
                value={newUser.role}
                onValueChange={(value) => setNewUser((prev) => ({ ...prev, role: value as UserRoleType }))}
              >
                <SelectTrigger className="w-full border-slate-700 bg-slate-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-slate-800 bg-slate-900">
                  <SelectItem value="owner">OWNER</SelectItem>
                  <SelectItem value="manager">MANAGER</SelectItem>
                  <SelectItem value="designer">DESIGNER</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {temporaryPassword && (
              <div className="rounded-md border border-teal-500/20 bg-teal-500/10 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-teal-300">
                  Temporary Password
                </p>
                <p className="mt-1 font-mono text-sm text-teal-100">{temporaryPassword}</p>
                <p className="mt-1 text-[11px] text-teal-200/80">
                  Share this once. It will not be shown again.
                </p>
              </div>
            )}

            {createError && (
              <p className="rounded-md border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-300">
                {createError}
              </p>
            )}

            <DialogFooter className="border-slate-800 bg-slate-900/40">
              <Button
                type="button"
                variant="outline"
                className="border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
                onClick={() => setIsCreateOpen(false)}
              >
                Close
              </Button>
              <Button
                type="submit"
                className="bg-sky-600 text-white hover:bg-sky-500"
                disabled={createUser.isPending}
              >
                {createUser.isPending ? 'Creating...' : 'Create Member'}
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
        <DialogContent className="max-w-md border-slate-800 bg-slate-950 text-slate-100">
          <DialogHeader>
            <DialogTitle>Edit Permissions</DialogTitle>
            <DialogDescription className="text-slate-400">
              Update role and account status for {editingUser?.full_name ?? 'user'}.
            </DialogDescription>
          </DialogHeader>

          <form className="space-y-4" onSubmit={handleUpdatePermissions}>
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Role</p>
              <Select value={editRole} onValueChange={(value) => setEditRole(value as UserRoleType)}>
                <SelectTrigger className="w-full border-slate-700 bg-slate-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-slate-800 bg-slate-900">
                  <SelectItem value="owner">OWNER</SelectItem>
                  <SelectItem value="manager">MANAGER</SelectItem>
                  <SelectItem value="designer">DESIGNER</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Account Status</p>
              <Select
                value={editIsActive ? 'active' : 'inactive'}
                onValueChange={(value) => setEditIsActive(value === 'active')}
              >
                <SelectTrigger className="w-full border-slate-700 bg-slate-900/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-slate-800 bg-slate-900">
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {editError && (
              <p className="rounded-md border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-300">
                {editError}
              </p>
            )}

            <DialogFooter className="border-slate-800 bg-slate-900/40">
              <Button
                type="button"
                variant="outline"
                className="border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
                onClick={() => setEditingUser(null)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                className="bg-sky-600 text-white hover:bg-sky-500"
                disabled={updateUser.isPending}
              >
                {updateUser.isPending ? 'Saving...' : 'Save Changes'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-200">Team Members</h2>
          {isOwner && (
            <Button
              className="bg-sky-600 hover:bg-sky-500 text-white"
              onClick={() => setIsCreateOpen(true)}
            >
              <UserPlus className="mr-2 h-4 w-4" /> Add Member
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
          <Card className="border-slate-800/60 bg-slate-900/40 backdrop-blur-sm shadow-md">
            <CardContent className="p-0">
              <Table>
                <TableHeader className="bg-slate-800/30">
                  <TableRow className="border-slate-800/60 hover:bg-transparent">
                    <TableHead className="text-slate-400">User</TableHead>
                    <TableHead className="text-slate-400">Role</TableHead>
                    <TableHead className="text-slate-400">Status</TableHead>
                    <TableHead className="text-slate-400">Contact</TableHead>
                    {isOwner && <TableHead className="text-right text-slate-400">Actions</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users?.map((u) => (
                    <TableRow key={u.id} className="border-slate-800/60 hover:bg-slate-800/20">
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-xs font-bold text-slate-100 border border-slate-700">
                            {u.full_name?.charAt(0) || 'U'}
                          </div>
                          <span className="text-slate-200">{u.full_name}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={ROLE_COLORS[u.role as keyof typeof ROLE_COLORS]}>
                          <Shield className="mr-1 h-3 w-3" />
                          {u.role.toUpperCase()}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {u.is_active ? (
                          <div className="flex items-center gap-2 text-xs text-teal-400">
                            <UserCheck className="h-4 w-4" />
                            Active
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-xs text-slate-500">
                            <UserX className="h-4 w-4" />
                            Inactive
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                          <Mail className="h-3 w-3" />
                          {u.email}
                        </div>
                      </TableCell>
                      {isOwner && u.id !== currentUser?.id && (
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-slate-100">
                                <MoreVertical className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-48 bg-slate-900 border-slate-800">
                              <DropdownMenuItem
                                className="text-slate-300 hover:bg-slate-800 cursor-pointer"
                                onClick={() => openEditPermissions(u)}
                              >
                                Edit Permissions
                              </DropdownMenuItem>
                              <DropdownMenuItem 
                                className={`${u.is_active ? 'text-red-400 hover:bg-red-500/10' : 'text-teal-400 hover:bg-teal-500/10'} cursor-pointer`}
                                onClick={() => toggleUserStatus(u.id, u.is_active)}
                              >
                                {u.is_active ? 'Deactivate User' : 'Activate User'}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      )}
                      {u.id === currentUser?.id && isOwner && (
                        <TableCell className="text-right text-xs text-slate-500 italic pr-4">
                          You
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
