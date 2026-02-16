from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count
from .models import Post


def post_list(request):
    posts = Post.objects.filter(published=True).order_by('-created_at')[:20]
    return render(request, 'blog/post_list.html', {'posts': posts})


def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug, published=True)

    # Try to find related posts by shared keywords
    related_posts = []
    if post.keywords:
        kw_list = [kw.strip() for kw in post.keywords.split(',') if kw.strip()]
        if kw_list:
            q = Q()
            for kw in kw_list:
                q |= Q(keywords__icontains=kw)
            related_posts = list(
                Post.objects.filter(published=True)
                .filter(q)
                .exclude(pk=post.pk)
                .annotate(match_count=Count('pk'))
                .order_by('-created_at')
                .distinct()[:3]
            )

    # Fallback: fill remaining slots with latest posts
    if len(related_posts) < 3:
        exclude_ids = [post.pk] + [p.pk for p in related_posts]
        filler = (
            Post.objects.filter(published=True)
            .exclude(pk__in=exclude_ids)
            .order_by('-created_at')[: 3 - len(related_posts)]
        )
        related_posts.extend(filler)

    return render(request, 'blog/post_detail.html', {
        'post': post,
        'related_posts': related_posts,
    })
