import { NextResponse } from 'next/server';
import { z } from 'zod';
import { extractKeywords } from '@/lib/keywords';

const bodySchema = z.object({ text: z.string().min(5), top: z.number().int().min(1).max(50).optional() });

export async function POST(req: Request) {
  try {
    const json = await req.json();
    const parsed = bodySchema.parse(json);
    const kws = extractKeywords(parsed.text, parsed.top ?? 10);
    return NextResponse.json({ keywords: kws });
  } catch (e) {
    return NextResponse.json({ error: 'invalid' }, { status: 400 });
  }
}
