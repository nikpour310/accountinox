export default function Home() {
  return (
    <section className="text-center py-20">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-4xl font-bold text-primary mb-4">خوش آمدید به Accountinox</h1>
        <p className="text-lg text-gray-700 mb-6">خرید امن و سریع اکانت‌ها با پنل مدیریت کامل</p>
        <div className="flex justify-center gap-4">
          <a href="/auth" className="px-6 py-3 rounded-md bg-primary text-white">ثبت‌نام / ورود</a>
          <a href="/shop" className="px-6 py-3 rounded-md border border-primary text-primary">مشاهده محصولات</a>
        </div>
      </div>
    </section>
  );
}
