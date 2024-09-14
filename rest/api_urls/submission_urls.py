from django.urls import path
from ..views.submission_views import *

urlpatterns = [
    path('', SubmissionBasicView.as_view(), name='submission-basic'),
    path('<int:submission_id>/', SubmissionDetailView.as_view(), name='submission-detail')
]
