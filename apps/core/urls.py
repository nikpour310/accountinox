from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('contact/', views.contact, name='contact'),
]
