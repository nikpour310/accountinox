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
    path('otp/login/', views.otp_login_page, name='otp_login'),
    path('otp/send/', views.send_otp, name='send_otp'),
    path('otp/verify/', views.verify_otp, name='verify_otp'),
    path('otp/verify-login/', views.verify_otp_login, name='verify_otp_login'),

    # ── Profile verification (phone / email change) ──
    path('profile/phone/send-code/', views.send_phone_change_code, name='send_phone_change_code'),
    path('profile/phone/verify/', views.verify_phone_change, name='verify_phone_change'),
    path('profile/email/send-code/', views.send_email_change_code, name='send_email_change_code'),
    path('profile/email/verify/', views.verify_email_change, name='verify_email_change'),
]
