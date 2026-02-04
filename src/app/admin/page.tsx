export default function AdminPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold">داشبورد ادمین</h1>
      <div className="mt-4">این پنل هنوز کامل نشده، اما مسیرها و مدل‌ها آماده‌اند.</div>
      <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        <a href="/admin/products" className="p-4 border rounded">محصولات</a>
        <a href="/admin/orders" className="p-4 border rounded">سفارش‌ها</a>
        <a href="/admin/users" className="p-4 border rounded">کاربران</a>
      </div>
    </div>
  );
}
