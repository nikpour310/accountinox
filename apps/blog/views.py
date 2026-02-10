from django.shortcuts import render, get_object_or_404
from .models import Post


def post_list(request):
    posts = Post.objects.filter(published=True).order_by('-created_at')[:20]
    return render(request, 'blog/post_list.html', {'posts': posts})


def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug, published=True)
    return render(request, 'blog/post_detail.html', {'post': post})
