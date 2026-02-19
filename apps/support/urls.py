from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    # User interface
    path('', views.support_index, name='chat'),
    path('start/', views.start_chat, name='start_chat'),
    path('chat/', views.chat_room, name='chat_room'),
    path('rate/<int:session_id>/', views.rate_session, name='rate_session'),
    path('session/<int:session_id>/', views.user_open_session, name='user_open_session'),
    path('session/<int:session_id>/close/', views.user_close_session, name='user_close_session'),
    path('session/<int:session_id>/reopen/', views.user_reopen_session, name='user_reopen_session'),
    path('send/', views.send_message, name='send_message'),
    path('messages/', views.get_messages, name='get_messages'),
    path('poll/', views.poll_messages, name='poll_messages'),
    path('typing/update/', views.typing_update, name='typing_update'),
    path('typing/status/', views.typing_status, name='typing_status'),
    path('push/subscribe/', views.push_subscribe, name='push_subscribe'),
    path('push/unsubscribe/', views.push_unsubscribe, name='push_unsubscribe'),
    path('push/debug/', views.push_debug, name='push_debug'),
    
    # Operator/Admin interface
    path('operator/', views.operator_dashboard, name='operator_dashboard'),
    path('operator/session/<int:session_id>/', views.operator_session_view, name='operator_session'),
    path('operator/send/', views.operator_send_message, name='operator_send_message'),
    path('operator/presence/', views.operator_presence, name='operator_presence'),
    path('operator/unread-status/', views.operator_unread_status, name='operator_unread_status'),
    path('operator/<int:session_id>/close/', views.close_session, name='close_session'),
]
