from django.urls import path
from ..views.category_views import *

urlpatterns = [
    path('', CategoryView.as_view(), name='category-list'),
    path('<int:category_id>/', CategoryView.as_view(), name='category-detail'),
]
