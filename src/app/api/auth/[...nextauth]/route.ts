import NextAuth from 'next-auth';
import { authOptions } from '@/lib/authOptions';

const _handler = NextAuth(authOptions as any);
export { _handler as GET, _handler as POST };
