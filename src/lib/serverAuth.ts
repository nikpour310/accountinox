import { getServerSession } from 'next-auth';
import { authOptions } from '@/app/api/auth/[...nextauth]/route';

export async function getCurrentUser() {
  const session = await getServerSession(authOptions as any);
  // @ts-ignore
  return session?.user;
}

export function requireAdmin(user: any) {
  if (!user || user.role !== 'ADMIN') throw new Error('unauthorized');
}
