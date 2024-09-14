from django.urls import path
from ..views.user_views import *

urlpatterns = [
    # path('management', UserMangementView.as_view(), name='user-management'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('submissions/', UserSubmissionView.as_view(), name='user-submission'),
]