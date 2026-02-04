// Centralized NextAuth options for reuse across server and routes.
import CredentialsProvider from 'next-auth/providers/credentials';
import GoogleProvider from 'next-auth/providers/google';
import { prisma } from '@/lib/prisma';
import argon2 from 'argon2';

// Basic in-memory rate limiter for credential sign-ins (per identifier). Dev-only.
const _loginAttempts: Map<string, { count: number; last: number }> = new Map();

export const authOptions: any = {
  providers: [
    CredentialsProvider({
      name: 'Credentials',
      credentials: {
        email: { label: 'Email', type: 'text' },
        phone: { label: 'Phone', type: 'text' },
        password: { label: 'Password', type: 'password' }
      },
      async authorize(credentials: any) {
        const identifier = credentials?.email ?? credentials?.phone;
        if (!identifier || !credentials?.password) return null;

        // rate limit checks (dev only)
        try {
          const now = Date.now();
          const state = _loginAttempts.get(identifier) ?? { count: 0, last: now };
          if (now - state.last > 15 * 60_000) {
            state.count = 0;
          }
          state.count += 1;
          state.last = now;
          _loginAttempts.set(identifier, state);
          if (state.count > 10) {
            const _payload = { data: { action: 'auth:login:rate_limited', actorId: null, meta: { identifier: identifier } } };
            await prisma.auditLog.create(_payload as any);
            return null;
          }
        } catch (e) {
          // noop
        }

        const user = credentials.email
          ? await prisma.user.findUnique({ where: { email: credentials.email } })
          : await prisma.user.findUnique({ where: { phone: credentials.phone } });
        if (!user || !user.password) {
          const _payload = { data: { action: 'auth:login:fail', actorId: null, meta: { identifier: identifier, reason: 'no-user-or-no-password' } } };
          await prisma.auditLog.create(_payload as any);
          return null;
        }
        const ok = await argon2.verify(user.password, credentials.password);
        if (!ok) {
          const _payload = { data: { action: 'auth:login:fail', actorId: user.id, meta: { identifier: identifier, reason: 'bad-password' } } };
          await prisma.auditLog.create(_payload as any);
          return null;
        }
        {
          const _payload = { data: { action: 'auth:login:success', actorId: user.id, meta: { identifier: identifier } } };
          await prisma.auditLog.create(_payload as any);
        }
  try { _loginAttempts.delete(credentials.email ?? credentials.phone); } catch (e) { /* ignore */ }
        return { id: user.id, email: user.email, name: user.name, role: user.role };
      }
    }),
    GoogleProvider({ clientId: process.env.GOOGLE_CLIENT_ID || '', clientSecret: process.env.GOOGLE_CLIENT_SECRET || '' })
  ],
  session: { strategy: 'jwt' },
  callbacks: {
    async jwt({ token, user }: any) {
      if (user) token.role = user.role;
      return token;
    },
    async session({ session, token }: any) {
      // @ts-ignore
      session.user.role = token.role;
      return session;
    }
  },
  secret: process.env.NEXTAUTH_SECRET
};
