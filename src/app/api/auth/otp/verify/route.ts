import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const phone = body?.phone;
    const code = body?.code;
    if (!phone || !code) return NextResponse.json({ error: 'phone and code required' }, { status: 400 });

    const record = await prisma.phoneVerification.findFirst({
      where: { phone, code, used: false },
      orderBy: { createdAt: 'desc' }
    });
    if (!record) return NextResponse.json({ error: 'invalid code' }, { status: 400 });
    if (record.expiresAt < new Date()) return NextResponse.json({ error: 'code expired' }, { status: 400 });

    await prisma.phoneVerification.update({ where: { id: record.id }, data: { used: true } });

    // Optionally create or fetch user by phone
    let user = await prisma.user.findUnique({ where: { phone } });
    if (!user) {
      user = await prisma.user.create({ data: { phone } });
    }

    // In a real flow we would create a session/token here. NextAuth credential signin can be used.
    return NextResponse.json({ ok: true, user: { id: user.id, phone: user.phone } });
  } catch (err) {
    return NextResponse.json({ error: (err as any)?.message || String(err) }, { status: 500 });
  }
}
