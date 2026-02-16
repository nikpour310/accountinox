from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify


class Command(BaseCommand):
    help = 'Seed demo Services and Products for local testing'

    def handle(self, *args, **options):
        from apps.shop.models import Service, Product, Category

        demo_services = [
            {
                'name': 'پرداخت آنلاین',
                'description': 'راهکارهای پرداخت با درگاه‌های معتبر و رابط کاربری ساده.',
                'icon': 'credit-card',
                'order': 10,
                'products': [
                    {'title': 'درگاه بانکی استاندارد', 'price': '199000.00', 'description': 'درگاه پرداخت امن برای فروشگاه‌ها'},
                    {'title': 'درگاه پرداخت اختصاصی', 'price': '499000.00', 'description': 'راه‌اندازی درگاه با برند اختصاصی شما'},
                ],
            },
            {
                'name': 'مدیریت اشتراک',
                'description': 'سرویس عضویت و اشتراک با پرداخت دوره‌ای و مدیریت اعضا.',
                'icon': 'users',
                'order': 20,
                'products': [
                    {'title': 'عضویت پایه', 'price': '99000.00', 'description': 'دسترسی به محتوا و امکانات پایه'},
                    {'title': 'عضویت حرفه‌ای', 'price': '299000.00', 'description': 'دسترسی کامل + پشتیبانی ویژه'},
                ],
            },
            {
                'name': 'امنیت و پشتیبانی',
                'description': 'خدمات پشتیبانی و راه‌حل‌های امنیتی برای سایت‌ها.',
                'icon': 'shield-check',
                'order': 30,
                'products': [
                    {'title': 'پک امنیت پایه', 'price': '149000.00', 'description': 'بررسی امنیتی و گزارش اولیه'},
                    {'title': 'سرویس پشتیبانی سالیانه', 'price': '599000.00', 'description': 'پشتیبانی و نگهداری فنی 12 ماه'},
                ],
            },
        ]

        created = 0
        with transaction.atomic():
            for svc in demo_services:
                slug = slugify(svc['name'])
                service_obj, svc_created = Service.objects.get_or_create(slug=slug, defaults={
                    'name': svc['name'],
                    'description': svc.get('description', ''),
                    'icon': svc.get('icon', ''),
                    'active': True,
                    'order': svc.get('order', 100),
                })
                if not svc_created:
                    # ensure fields updated
                    service_obj.name = svc['name']
                    service_obj.description = svc.get('description', '')
                    service_obj.icon = svc.get('icon', '')
                    service_obj.active = True
                    service_obj.order = svc.get('order', 100)
                    service_obj.save()

                for p in svc.get('products', []):
                    pslug = slugify(p['title'])
                    # Ensure a category exists for demo products
                    category_obj, _ = Category.objects.get_or_create(name='خدمات', slug='services')
                    prod_obj, prod_created = Product.objects.get_or_create(slug=pslug, defaults={
                        'title': p['title'],
                        'description': p.get('description', ''),
                        'price': p.get('price', '0.00'),
                        'category': category_obj,
                        'service': service_obj,
                    })
                    if not prod_created:
                        prod_obj.title = p['title']
                        prod_obj.description = p.get('description', '')
                        prod_obj.price = p.get('price', '0.00')
                        prod_obj.category = category_obj
                        prod_obj.service = service_obj
                        prod_obj.save()
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded demo services and {created} products."))
