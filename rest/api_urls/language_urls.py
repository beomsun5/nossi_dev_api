from django.urls import path
from ..views.language_views import *

urlpatterns = [
    path('', LanguageView.as_view(), name='language-list'),
    path('<int:language_id>/', LanguageView.as_view(), name='language-detail'),
]
