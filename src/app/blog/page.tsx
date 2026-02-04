import { prisma } from '@/lib/prisma';

export default async function BlogPage() {
  if (process.env.SKIP_DB === 'true') {
    return (
      <div>
        <h2 className="text-2xl font-bold mb-4">بلاگ</h2>
        <div className="text-sm text-gray-600">(داده‌ها در این بیلد موقتا بارگذاری نشده‌اند)</div>
      </div>
    );
  }

  const posts = await prisma.post.findMany({ where: { published: true }, take: 10 });
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">بلاگ</h2>
      <div className="space-y-4">
        {posts.map((p) => (
          <article key={p.id} className="border rounded p-4">
            <h3 className="font-semibold">{p.title}</h3>
            <p className="text-sm text-gray-600">{p.summary}</p>
            <a href={`/blog/${p.slug}`} className="text-primary">خواندن</a>
          </article>
        ))}
      </div>
    </div>
  );
}
