from django.db import models
from django.utils.text import slugify
from django.urls import reverse
from .extractor2 import extract_keywords


class Post(models.Model):
    title = models.CharField('عنوان', max_length=255)
    slug = models.SlugField('اسلاگ', unique=True, blank=True)
    content = models.TextField('محتوا')
    featured_image = models.ImageField('تصویر شاخص', upload_to='blog/', blank=True, null=True)
    seo_title = models.CharField('عنوان SEO', max_length=255, blank=True)
    seo_description = models.TextField('توضیحات SEO', blank=True)
    keywords = models.TextField('کلمات کلیدی', blank=True)
    published = models.BooleanField('منتشرشده', default=False)
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)

    class Meta:
        verbose_name = 'پست بلاگ'
        verbose_name_plural = 'پست‌های بلاگ'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:200]
        # auto-extract keywords if empty
        if not self.keywords:
            kws = extract_keywords(self.content)
            self.keywords = ','.join(kws)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('blog:post_detail', args=[self.slug])

    @property
    def keywords_list(self):
        """Return keywords as a cleaned list for template iteration."""
        if not self.keywords:
            return []
        return [kw.strip() for kw in self.keywords.split(',') if kw.strip()]

    def __str__(self):
        return self.title


class PostFAQ(models.Model):
    post = models.ForeignKey(Post, related_name='faqs', on_delete=models.CASCADE,
                             verbose_name='پست')
    question = models.CharField('سوال', max_length=255)
    answer = models.TextField('پاسخ')

    class Meta:
        verbose_name = 'سوال متداول پست'
        verbose_name_plural = 'سوالات متداول پست'

    def __str__(self):
        return self.question
