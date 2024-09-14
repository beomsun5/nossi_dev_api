from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from rest_framework import status
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.conf import settings
from django.shortcuts import redirect
from .models import Profile
import requests

KAKAO_ADMIN_KEY = settings.KAKAO_ADMIN_KEY

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        print("populate_user method called")
        user = super().populate_user(request, sociallogin, data)
        social_uid = data.get('id', -1)
        if social_uid == -1: # Not New User
            print(f"Login process!!\n")
            user.email = data.get('email', 'email@none.com')
            user.username = data.get('username', 'Anonymous')
        else: # New User
            print(f"Register process!!\n")
            properties = data.get('properties')
            kakao_account = data.get('kakao_account')
            user.social_uid = social_uid
            user.email = kakao_account.get('email', 'email@none.com')
            user.email_verified = kakao_account.get('is_email_verified', False)
            user.username = properties.get('nickname', 'Anonymous')
            user.last_login = sociallogin.account.last_login
            user.join_date = sociallogin.account.date_joined
            user.provider = sociallogin.account.provider
            user.provider_id = sociallogin.account.uid
            user.refresh_token = sociallogin.token.token_secret
        return user

    def save_user(self, request, sociallogin, form=None):
        """
        This method is responsible for saving the User model.
        """
        user = self.populate_user(request, sociallogin, sociallogin.account.extra_data)

        # If a form is provided (usually during signup), apply the form data to the user
        if form:
            user = form.save(commit=False)
        
        user.save()

        # Create or update the profile
        if sociallogin.account.provider == "kakao":
            properties = sociallogin.account.extra_data.get('properties', {})
            profile, created = Profile.objects.get_or_create(user_id=user)
            profile.profile_image = properties.get('profile_image', '')
            profile.save()

        sociallogin.connect(request, user)
        print(f"Connected SocialAccount: {sociallogin.account}, to User: {user}")

        return user
        # request.session['user_email'] = user.email
        # # request.session['social_uid'] = user.social_uid
        # request.session['provider'] = user.provider
        # request.session['access_token'] = sociallogin.token.token
        # request.session['refresh_token'] = sociallogin.token.token_secret
        # request.session['message'] = "Login Success" if user.last_login else "User Register successfully"

        # # Debugging: print session data to check if it has been set correctly
        # print(f"Session Data Before Redirect: {request.session.items()}")

        # return redirect('kakao_login_home_redirect')
    
    def disconnect(self, provider, access_token, social_id=None):
        # 각 소셜에 대한 연결 끊기 API 호출
        if provider == 'kakao':
            # 카카오 연결끊기 로직
            if social_id is None:
                response = requests.post(
                    "https://kapi.kakao.com/v1/user/unlink",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if response.status_code != 200:
                    logger.info("disconnect kakao error")
            else:
                headers = {"Authorization": f'KakaoAK {KAKAO_ADMIN_KEY}'}
                logout_response = requests.post(
                    'https://kapi.kakao.com/v1/user/logout',
                    data={
                        'target_id_type': 'user_id',
                        'target_id': social_id
                    },
                    headers=headers
                )
        else:
            raise NotImplementedError("Disconnect for another_sns is not implemented")