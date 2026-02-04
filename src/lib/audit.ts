import { prisma } from './prisma';

export async function logAction(action: string, actorId?: string, meta?: any) {
  await prisma.auditLog.create({ data: { action, actorId, meta } });
}
