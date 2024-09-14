from django.urls import path, include

urlpatterns = [
    # path('admin/', include('rest.api_urls.admin_urls')),
    path('users/', include('rest.api_urls.user_urls')),
    path('categories/', include('rest.api_urls.category_urls')),
    path('problems/', include('rest.api_urls.problem_urls')),
    path('submissions/', include('rest.api_urls.submission_urls')),
    path('languages/', include('rest.api_urls.language_urls')),
    path('max-constraints/', include('rest.api_urls.max_constraint_urls')),
]