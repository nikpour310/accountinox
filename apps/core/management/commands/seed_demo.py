from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.core.models import SiteSettings, GlobalFAQ
from apps.shop.models import Category, Product, AccountItem
from apps.blog.models import Post
from django.conf import settings
import random


class Command(BaseCommand):
    help = 'Seed demo data: admin user, site settings, categories, products, blog posts, account items'

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(is_superuser=True).exists():
            print('Creating superuser: admin@example.com / pass: admin')
            User.objects.create_superuser('admin@example.com', 'admin@example.com', 'admin')

        ss = SiteSettings.load()
        ss.site_name = 'Accountinox Demo'
        ss.tailwind_mode = 'local'
        ss.save()

        cat, _ = Category.objects.get_or_create(name='اکانت‌های عمومی', slug='general')
        for i in range(1, 6):
            p, _ = Product.objects.get_or_create(title=f'حساب نمونه {i}', slug=f'sample-{i}', defaults={'price': 10000 + i * 1000, 'description': 'توضیحات نمونه'})
            # create some account items
            for j in range(3):
                ai = AccountItem(product=p)
                try:
                    ai.set_plain(username=f'user{i}{j}', password=f'pass{i}{j}', notes='demo')
                except Exception:
                    # possible missing FERNET_KEY during seed; store as empty bytes to allow migrations
                    ai.username_encrypted = b''
                    ai.password_encrypted = b''
                ai.save()

        # sample global FAQ
        GlobalFAQ.objects.get_or_create(question='تحویل چگونه است؟', defaults={'answer': 'تحویل بلافاصله پس از پرداخت'})

        # sample blog post
        Post.objects.get_or_create(title='خوش‌آمد به Accountinox', slug='welcome', defaults={'content': '<p>این یک پست نمونه است.</p>', 'published': True})

        self.stdout.write(self.style.SUCCESS('Demo data seeded.'))
