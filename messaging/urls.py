from django.urls import path

from .views import (
    AssignConversationView,
    ConversationDetailView,
    ConversationListCreateView,
    ConversationMessagesView,
    ConversationStatusView,
    MessagingNotificationsView,
    MessagingUnreadCountView,
    StaffDirectoryView,
)

urlpatterns = [
    path('conversations/', ConversationListCreateView.as_view(), name='messaging-conversations'),
    path('conversations/<int:conversation_id>/', ConversationDetailView.as_view(), name='messaging-conversation-detail'),
    path('conversations/<int:conversation_id>/messages/', ConversationMessagesView.as_view(), name='messaging-conversation-messages'),
    path('conversations/<int:conversation_id>/assign/', AssignConversationView.as_view(), name='messaging-conversation-assign'),
    path('conversations/<int:conversation_id>/status/', ConversationStatusView.as_view(), name='messaging-conversation-status'),
    path('staff/', StaffDirectoryView.as_view(), name='messaging-staff-directory'),
    path('notifications/', MessagingNotificationsView.as_view(), name='messaging-notifications'),
    path('notifications/unread-count/', MessagingUnreadCountView.as_view(), name='messaging-unread-count'),
]