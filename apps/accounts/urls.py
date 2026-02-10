from django.urls import path
from apps.accounts import views

app_name = 'accounts'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('orders/', views.order_list, name='orders'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('profile/', views.profile_settings, name='profile'),
    path('addresses/', views.address_book, name='addresses'),
    path('addresses/<int:address_id>/edit/', views.edit_address, name='edit_address'),
    path('addresses/<int:address_id>/delete/', views.delete_address, name='delete_address'),
    path('addresses/<int:address_id>/default/', views.set_default_address, name='set_default_address'),
    path('otp/send/', views.send_otp, name='send_otp'),
    path('otp/verify/', views.verify_otp, name='verify_otp'),
]
