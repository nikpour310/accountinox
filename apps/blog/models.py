from django.db import models
from django.utils.text import slugify
from django.urls import reverse
from .extractor2 import extract_keywords


class Post(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    content = models.TextField()
    featured_image = models.ImageField(upload_to='blog/', blank=True, null=True)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.TextField(blank=True)
    keywords = models.TextField(blank=True)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

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

    def __str__(self):
        return self.title


class PostFAQ(models.Model):
    post = models.ForeignKey(Post, related_name='faqs', on_delete=models.CASCADE)
    question = models.CharField(max_length=255)
    answer = models.TextField()

    def __str__(self):
        return self.question
