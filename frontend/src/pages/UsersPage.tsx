import { 
  UserPlus, 
  Shield, 
  UserX, 
  UserCheck, 
  Mail, 
  MoreVertical 
} from 'lucide-react';
import { useUsers, useUpdateUser } from '@/hooks/useUsers';
import { useAuth } from '@/hooks/useAuth';
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
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '../components/ui/dropdown-menu';

const ROLE_COLORS = {
  owner: 'bg-teal-500/10 text-teal-400 border-teal-500/30',
  manager: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
  designer: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30',
};

export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const { data: users, isLoading } = useUsers();
  const updateUser = useUpdateUser();
  
  const isOwner = currentUser?.role === 'owner';

  const toggleUserStatus = (userId: string, currentStatus: boolean) => {
    updateUser.mutate({ id: userId, payload: { is_active: !currentStatus } });
  };

  return (
    <ShellPage
      title="User Management"
      description="Manage team access and role-based permissions."
    >
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-200">Team Members</h2>
          {isOwner && (
            <Button className="bg-sky-600 hover:bg-sky-500 text-white">
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
                              <DropdownMenuItem className="text-slate-300 hover:bg-slate-800 cursor-pointer">
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
