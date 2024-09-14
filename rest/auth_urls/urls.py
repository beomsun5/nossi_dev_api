from django.urls import path, include
from ..views.auth_views import *

urlpatterns = [
### 자체 로그인 (only depending on dj_rest_auth)
    path('', include('dj_rest_auth.urls')),
    path('', include('dj_rest_auth.registration.urls')),
### 소셜 로그인 (allauth + dj_rest_auth)
    ### Kakao 소셜 로그인
    path('kakao/user/', kakao_show_verified, name='kakao_show_verified'),
    path('kakao/login/', kakao_login, name='kakao_login'),
    path('kakao/login/callback/', kakao_callback, name='kakao_callback'),
    path('kakao/login/finalize/', KakaoLoginView.as_view(), name='kakao_login_finalize'),
    # path('kakao/login/home-redirect/', kakao_login_home_redirect, name='kakao_login_home_redirect'),
    path('kakao/logout/', kakao_logout, name='kakao_logout'),
    path('kakao/logout/direct/', kakao_direct_logout, name='kakao_direct_logout'),
    # path('kakao/logout/home-redirect/', kakao_logout_home_redirect, name='kakao_logout_home_redirect'),
    path('kakao/unlink/', kakao_unlink, name='kakao_unlink'),
    path('kakao/refresh-token/', kakao_refresh_token, name="kakao_refresh_token"),
### 소셜 로그인 (only depending on allauth)
    # path('', include('allauth.urls')),
    # path('kakao/login/', kakao_login, name='kakao_login'),
    # path('kakao/login/home-redirect/', kakao_login_home_redirect, name='kakao_login_home_redirect'),
    # path('kakao/logout/', kakao_logout, name='kakao_logout'),
    # path('kakao/logout/home-redirect/', kakao_logout_home_redirect, name='kakao_logout_home_redirect'),
    # path('kakao/unlink/', kakao_unlink, name='kakao_unlink'),
]