import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function GET() {
  const products = await prisma.product.findMany({ where: { stock: { gt: 0 } } });
  const posts = await prisma.post.findMany({ where: { published: true } });

  const urls = [
    { loc: '/', changefreq: 'daily' },
    ...products.map((p) => ({ loc: `/product/${p.slug}`, changefreq: 'weekly' })),
    ...posts.map((p) => ({ loc: `/blog/${p.slug}`, changefreq: 'monthly' }))
  ];

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
  <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    ${urls
      .map(
        (u) => `
      <url>
        <loc>${process.env.NEXTAUTH_URL || 'http://localhost:3000'}${u.loc}</loc>
        <changefreq>${u.changefreq}</changefreq>
      </url>`
      )
      .join('\n')}
  </urlset>`;

  return new NextResponse(xml, { headers: { 'Content-Type': 'application/xml' } });
}
