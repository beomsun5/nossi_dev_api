from django.urls import path, include

urlpatterns = [
    path('api/v1/', include('rest.api_urls.__init__')),  # Prefix for API URLs
    path('accounts/', include('dj_rest_auth.urls')),
    path('accounts/', include("dj_rest_auth.registration.urls")),
    path('accounts/', include('rest.auth_urls.urls')),  # Prefix for Auth URLs
]