import pkg from '@prisma/client';
const { PrismaClient } = pkg as any;

declare global {
  // eslint-disable-next-line no-var
  var prisma: any | undefined;
}

export const prisma = (global.prisma as any) ?? new PrismaClient();
if (process.env.NODE_ENV !== 'production') (global as any).prisma = prisma;
