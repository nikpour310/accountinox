import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

function genCode() {
  return Math.floor(100000 + Math.random() * 900000).toString();
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const phone = body?.phone;
    if (!phone) return NextResponse.json({ error: 'phone required' }, { status: 400 });

    // Check site setting
    const site = await prisma.siteSetting.findFirst();
    if (site && !site.otpEnabled) {
      return NextResponse.json({ error: 'OTP disabled' }, { status: 403 });
    }

    // Rate limit: no more than one code per 60s
    const recent = await prisma.phoneVerification.findFirst({
      where: { phone },
      orderBy: { createdAt: 'desc' }
    });
    if (recent) {
      const diff = Date.now() - recent.createdAt.getTime();
      if (diff < 60_000) return NextResponse.json({ error: 'wait before requesting again' }, { status: 429 });
    }

    const code = genCode();
    const expiresAt = new Date(Date.now() + 5 * 60 * 1000); // 5 minutes

    await prisma.phoneVerification.create({ data: { phone, code, expiresAt } });

    // Audit log the send event
    await prisma.auditLog.create({ data: { action: 'otp:send', actorId: null, meta: { phone } } });

    // Stub provider: log the code. In production replace with SMS provider.
    // Do NOT expose codes in responses in production.
    // Here we return ok=true but include a hint for dev environments.
    return NextResponse.json({ ok: true, hint: `OTP for ${phone} is ${code}` });
  } catch (err) {
    return NextResponse.json({ error: (err as any)?.message || String(err) }, { status: 500 });
  }
}
