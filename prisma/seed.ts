import pkg from '@prisma/client';
import argon2 from 'argon2';

const { PrismaClient } = pkg as any;
const prisma = new PrismaClient();

async function main() {
  const pass = await argon2.hash('adminpass123');
  await prisma.siteSetting.upsert({
    where: { id: 'default' },
    update: {},
    create: {
      id: 'default',
      siteTitle: 'Accountinox',
      tailwindMode: 'local',
      otpEnabled: false
    }
  });

  const admin = await prisma.user.upsert({
    where: { email: 'admin@accountinox.test' },
    update: {},
    create: {
      email: 'admin@accountinox.test',
      name: 'Admin',
      password: pass,
      role: 'ADMIN'
    }
  });

  const cat = await prisma.category.upsert({
    where: { slug: 'accounts' },
    update: {},
    create: { name: 'اکانت‌ها', slug: 'accounts' }
  });

  const prod = await prisma.product.create({
    data: {
      title: 'Netflix Premium 1 Month',
      slug: 'netflix-premium-1m',
      price: 100000,
      stock: 10,
      categoryId: cat.id
    }
  });

  const post = await prisma.post.create({
    data: {
      title: 'راهنمای خرید امن',
      slug: 'buy-safe',
      content: 'محتوای نمونه برای تولید کلیدواژه و تست',
      published: true,
      authorId: admin.id
    }
  });

  console.log({ admin: admin.email, product: prod.slug, post: post.slug });
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => {
    prisma.$disconnect();
  });