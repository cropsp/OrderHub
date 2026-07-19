import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usersApi } from '@/api/users';

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: usersApi.list,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: usersApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: any }) => usersApi.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}

export function useUserShopAccess(userId: string | null) {
  return useQuery({
    queryKey: ['users', userId, 'shop-access'],
    queryFn: () => usersApi.getShopAccess(userId as string),
    enabled: Boolean(userId),
  });
}

export function useSetUserShopAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      shop_ids,
      unassign_orders,
    }: {
      id: string;
      shop_ids: string[];
      unassign_orders?: boolean;
    }) => usersApi.setShopAccess(id, { shop_ids, unassign_orders }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users', variables.id, 'shop-access'] });
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
  });
}

export function useUpdatePreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: usersApi.updatePreferences,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users', 'me'] });
      queryClient.invalidateQueries({ queryKey: ['auth-user'] });
    },
  });
}
