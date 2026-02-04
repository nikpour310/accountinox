import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getCurrentUser, requireAdmin } from '@/lib/serverAuth';
import { z } from 'zod';

export async function GET() {
  const settings = await prisma.siteSetting.findFirst();
  return NextResponse.json(settings ?? {});
}

const bodySchema = z.object({ tailwindMode: z.enum(['cdn', 'local']).optional(), otpEnabled: z.boolean().optional() });

export async function PATCH(req: Request) {
  try {
    const user = await getCurrentUser();
    requireAdmin(user);
    const body = await req.json();
    const data = bodySchema.parse(body);
    const s = await prisma.siteSetting.updateMany({ where: {}, data });
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json({ error: e.message || 'error' }, { status: 403 });
  }
}
