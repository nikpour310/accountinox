import './globals.css';
import { prisma } from '@/lib/prisma';
import React from 'react';

export const metadata = {
  title: 'Accountinox',
  description: 'فروشگاه و پنل مدیریت Accountinox'
};

async function getTailwindMode() {
  try {
    const s = await prisma.siteSetting.findFirst();
    return s?.tailwindMode ?? 'local';
  } catch (e) {
    return 'local';
  }
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const mode = await getTailwindMode();
  return (
    <html lang="fa" dir="rtl">
      <head>
        {mode === 'cdn' ? (
          // eslint-disable-next-line react/no-danger
          <script dangerouslySetInnerHTML={{ __html: `/* tailwind CDN loaded */` }} />
        ) : null}
      </head>
      <body className="font-vazir bg-white text-gray-900">
        <div className="min-h-screen bg-gradient-to-b from-primary/10 to-white">
          {/* header */}
          <header className="container mx-auto p-4 flex justify-between items-center">
            <div className="text-xl font-bold text-primary">Accountinox</div>
            <nav>
              <a href="/shop" className="mx-2 text-accent">فروشگاه</a>
              <a href="/blog" className="mx-2">بلاگ</a>
              <a href="/auth" className="mx-2">ورود</a>
            </nav>
          </header>

          <main className="container mx-auto p-4">{children}</main>

          <footer className="mt-8 border-t py-6">
            <div className="container mx-auto text-center">© {new Date().getFullYear()} Accountinox</div>
          </footer>
        </div>
      </body>
    </html>
  );
}
