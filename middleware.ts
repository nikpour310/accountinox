import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';

const securityHeaders = {
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'Permissions-Policy': 'geolocation=()',
  'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
  'Content-Security-Policy': "default-src 'self' 'unsafe-inline' https:"
};

export function withSecurityHeaders(res: Response | NextResponse) {
  for (const [k, v] of Object.entries(securityHeaders)) {
    try { res.headers.set(k, v); } catch (e) {}
  }
  return res;
}

export function middleware(req: NextRequest) {
  const url = req.nextUrl.clone();
  if (url.pathname.startsWith('/admin')) {
    // Use NextAuth JWT token (server-side) to ensure user has ADMIN role.
    // getToken will return the decoded token when NEXTAUTH_SECRET is set.
    // If token missing or role !== ADMIN -> redirect to /auth
    return (async () => {
      try {
        const token = await getToken({ req, secret: process.env.NEXTAUTH_SECRET });
        if (!token || token.role !== 'ADMIN') {
          url.pathname = '/auth';
          const r = NextResponse.redirect(url);
          return withSecurityHeaders(r);
        }
        const r = NextResponse.next();
        return withSecurityHeaders(r);
      } catch (err) {
        url.pathname = '/auth';
        const r = NextResponse.redirect(url);
        return withSecurityHeaders(r);
      }
    })();
  }
  const r = NextResponse.next();
  return withSecurityHeaders(r);
}

export const config = {
  matcher: ['/admin/:path*']
};