import NextAuth from 'next-auth';
import CredentialsProvider from 'next-auth/providers/credentials';
import GoogleProvider from 'next-auth/providers/google';
import { prisma } from '@/lib/prisma';
import argon2 from 'argon2';

const options = {
  providers: [
    CredentialsProvider({
      name: 'Credentials',
      credentials: {
        email: { label: 'Email', type: 'text' },
        password: { label: 'Password', type: 'password' }
      },
      async authorize(credentials: any) {
        if (!credentials?.email || !credentials?.password) return null;
        const user = await prisma.user.findUnique({ where: { email: credentials.email } });
        if (!user || !user.password) {
          await prisma.auditLog.create({ data: { action: 'auth:login:fail', actorId: null, meta: { email: credentials.email, reason: 'no-user-or-no-password' } } );
          return null;
        }
        const ok = await argon2.verify(user.password, credentials.password);
        if (!ok) {
          await prisma.auditLog.create({ data: { action: 'auth:login:fail', actorId: user.id, meta: { email: credentials.email, reason: 'bad-password' } } );
          return null;
        }
        await prisma.auditLog.create({ data: { action: 'auth:login:success', actorId: user.id, meta: { email: credentials.email } } );
        return { id: user.id, email: user.email, name: user.name, role: user.role };
      }
    }),
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID || '',
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || ''
    })
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

export { options as authOptions };

export default NextAuth(options as any);
