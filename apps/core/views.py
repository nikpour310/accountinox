from django.shortcuts import render
from .models import GlobalFAQ


def landing(request):
    faqs = GlobalFAQ.objects.all()[:10]
    return render(request, 'landing.html', {'faqs': faqs})


def terms(request):
    return render(request, 'terms.html')


def privacy(request):
    return render(request, 'privacy.html')


def contact(request):
    return render(request, 'contact.html')
