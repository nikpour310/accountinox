import { prisma } from '@/lib/prisma';

export default async function ShopPage() {
  const products = await prisma.product.findMany({ take: 12 });
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">فروشگاه</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {products.map((p) => (
          <div key={p.id} className="border rounded p-4">
            <h3 className="font-semibold">{p.title}</h3>
            <div className="text-sm text-gray-500">قیمت: {p.price} تومان</div>
            <a href={`/product/${p.slug}`} className="mt-2 inline-block text-primary">مشاهده</a>
          </div>
        ))}
      </div>
    </div>
  );
}
