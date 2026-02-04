import { prisma } from '@/lib/prisma';

export default async function ProductPage({ params }: { params: { slug: string } }) {
  const product = await prisma.product.findUnique({ where: { slug: params.slug } });
  if (!product) return <div>محصول پیدا نشد</div>;
  return (
    <div>
      <h1 className="text-2xl font-bold">{product.title}</h1>
      <p className="mt-2">{product.description}</p>
      <div className="mt-4">قیمت: {product.price} تومان</div>
      <a href="/cart" className="inline-block mt-4 bg-primary text-white px-4 py-2 rounded">اضافه کردن به سبد</a>
    </div>
  );
}
