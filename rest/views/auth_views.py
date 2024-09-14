from django.shortcuts import redirect
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timedelta, datetime
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status
from ..models import *
from ..serializers import *
from allauth.socialaccount import signals
from allauth.socialaccount.providers.kakao import views as kakao_view
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from allauth.socialaccount.providers.kakao.views import KakaoOAuth2Adapter
from allauth.socialaccount.models import SocialAccount, SocialToken
from dj_rest_auth.registration.views import SocialLoginView, SocialAccountDisconnectView
from dj_rest_auth.views import LogoutView
import os
import requests
import json
import logging
from json.decoder import JSONDecodeError

# Get the logger instance
logger = logging.getLogger('django')

class CKakaoLoginView(SocialLoginView):
    adapter_class = KakaoOAuth2Adapter
    callback_url = "http://localhost:8080/account"
    client_class = OAuth2Client
    
    def post(self, request, *args, **kwargs):
        res = super().post(request, *args, **kwargs)
        print(self.user.username) # extra data 가져오기 가능
        return res
        
class KakaoLogoutView(LogoutView):
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    
    
@api_view(['GET'])
def kakao_login(request):
    return redirect(f"https://kauth.kakao.com/oauth/authorize?client_id={settings.KAKAO_REST_API_KEY}&redirect_uri={settings.SOCIAL_LOGIN_REDIRECT_URI}&response_type=code")


@api_view(['GET', 'POST'])
def kakao_callback(request):
    logger.info("Kakao callback initiated")
    
    code = request.GET.get("code")
    logger.debug(f"Authorization code received: {code}")

    """
    Access Token Request
    """
    try:
        token_req = requests.get(
            f"https://kauth.kakao.com/oauth/token?grant_type=authorization_code&client_id={settings.KAKAO_REST_API_KEY}&redirect_uri={settings.SOCIAL_LOGIN_REDIRECT_URI}&code={code}")
        token_req_json = token_req.json()
        access_token = token_req_json.get("access_token", "")
        error = token_req_json.get("error")
        
        if error is not None:
            logger.error(f"Kakao token retrieval failed: {error}")
            return Response({
                'error': 'Kakao Social Login Callback - Token Retrieval Fail',
                'detail': error},
                status=status.HTTP_502_BAD_GATEWAY
            )

        token_info = {
            'access_token': token_req_json.get("access_token", ""),
            'refresh_token': token_req_json.get("refresh_token", ""),
            'at_expires_in': timezone.now() + timedelta(seconds=token_req_json.get("expires_in", 0)),
            'rt_expires_in': timezone.now() + timedelta(seconds=token_req_json.get("refresh_token_expires_in", 0)),
        }

        logger.debug(f"Token information retrieved: {token_info}")

    except requests.RequestException as e:
        logger.error(f"Request to Kakao for token failed: {str(e)}", exc_info=True)
        return Response({
            'error': 'Kakao Social Login Callback - Token Retrieval Fail',
            'detail': str(e)},
            status=status.HTTP_502_BAD_GATEWAY
        )

    ### Email Request
    if not access_token:
        logger.error("Access token not found in Kakao response")
        return Response({
            'error': 'Kakao Social Login Callback Fail',
            'detail': 'No access token taken from KAKAO'},
            status=status.HTTP_502_BAD_GATEWAY
        )

    ### Kakao Profile Retrieval
    try:
        profile_request = requests.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        profile_json = profile_request.json()
        kakao_account = profile_json.get('kakao_account')
        email = kakao_account.get('email')
        logger.debug(f"Profile retrieved for email: {email}")

    except requests.RequestException as e:
        logger.error(f"Request to Kakao for profile failed: {str(e)}", exc_info=True)
        return Response({
            'error': 'Kakao Social Login Callback - Profile Retrieval Fail',
            'detail': str(e)},
            status=status.HTTP_502_BAD_GATEWAY
        )

    ### Sign-in(Login) Request
    try:
        user = User.objects.get(email=email)
        social_account = SocialAccount.objects.get(user=user)
        if social_account is None:
            logger.warning(f"Email exists but no social user associated: {email}")
            return Response({
                'error': 'Kakao Login Callback - Login Fail',
                'detail': 'email exists but not social user'
            }, status=status.HTTP_400_BAD_REQUEST
            )
        if social_account.provider != 'kakao':
            logger.warning(f"No matching social provider for user: {email}")
            return Response({
                'error': 'Kakao Login Callback - Login Fail',
                'detail': 'No matching social provider - Expected: Kakao'
            }, status=status.HTTP_400_BAD_REQUEST
            )

        logger.info(f"User found and authenticated: {user.id}")

        data = {'access_token': access_token, 'code': code}
        accept = requests.post(
            f"{settings.KAKAO_LOGIN_FINALIZE_URI}", data=data)
        accept_status = accept.status_code
        if accept_status != 200:
            logger.error(f"Finalizing login process failed with status: {accept_status}")
            return Response({
                'error': 'Kakao Login Callback - Login Fail',
                'detail': 'Failed to finalize login process'
            }, status=accept_status
            )
        accept_json = accept.json()
        logger.debug("Login process finalized successfully")

        try:
            social_token = SocialToken.objects.get(account=social_account)
            # Update the SocialToken fields with the new token information
            social_token.token = token_info['access_token']
            social_token.token_secret = token_info['refresh_token']
            social_token.expires_at = token_info['at_expires_in'].isoformat()
            social_token.save()
            logger.info(f"Social token updated for user: {user.id}")

        except SocialToken.DoesNotExist:
            logger.error(f"No SocialToken found for SocialAccount with id: {social_account.id}")
            return Response({
                "error": "Kakao Login Callback - Social Token Fail",
                "detail": f"No SocialToken found for SocialAccount with id: {social_account.id}"
            }, status=status.HTTP_404_NOT_FOUND)

        response = Response({
            'message': 'Kakao Login Callback - Login Success',
            'data': {
                'user_id': accept_json['user']['pk'],
                'username': accept_json['user']['username'],
            },
            'token': {
                'access': token_info['access_token'],
                'refresh': token_info['refresh_token'],
                'access_expire': token_info['at_expires_in'].isoformat(),
                'refresh_expire': token_info['rt_expires_in'].isoformat()
            }
        }, status=status.HTTP_200_OK)

        response.set_cookie(
            key='access',
            value=token_info['access_token'],
            expires=token_info['at_expires_in'].isoformat(),
            max_age=timedelta(minutes=5),
            httponly=True,  # Prevents JavaScript access to the cookie
            secure=True,  # Ensures the cookie is only sent over HTTPS
            samesite='None',  # Helps protect against CSRF attacks
        )

        # Set the 'refresh' token as a cookie
        response.set_cookie(
            key='refresh',
            value=token_info['refresh_token'],
            expires=token_info['rt_expires_in'].isoformat(),
            max_age=timedelta(days=7),
            httponly=True,  # Prevents JavaScript access to the cookie
            secure=True,  # Ensures the cookie is only sent over HTTPS
            samesite='None'  # Helps protect against CSRF attacks
        )

        logger.info(f"Login process completed successfully for user: {user.id}")
        return response

    ### Sign-Up(Register) Request
    except User.DoesNotExist:
        logger.info(f"User does not exist, proceeding with registration: {email}")
        data = {'access_token': access_token, 'code': code}
        accept = requests.post(
            f"{settings.KAKAO_LOGIN_FINALIZE_URI}", data=data)
        accept_status = accept.status_code
        if accept_status != 200:
            logger.error(f"Finalizing registration process failed with status: {accept_status}")
            return Response({
                'error': 'Kakao Login Callback - Login Fail',
                'detail': 'Failed to finalize login process'
            }, status=accept_status
            )
        accept_json = accept.json()
        logger.debug("Registration process finalized successfully")

        try:
            user = User.objects.get(email=email)
            social_account = SocialAccount.objects.get(user=user)
            social_token = SocialToken.objects.get(account=social_account)
            # Update the SocialToken fields with the new token information
            social_token.token = token_info['access_token']
            social_token.token_secret = token_info['refresh_token']
            social_token.expires_at = token_info['at_expires_in'].isoformat()
            social_token.save()
            logger.info(f"User registered and social token saved: {user.id}")

        except SocialToken.DoesNotExist:
            logger.error(f"No SocialToken found during registration for SocialAccount with id: {social_account.id}")
            return Response({
                "error": "Kakao Login Callback - Social Token Fail",
                "detail": f"No SocialToken found for SocialAccount with id: {social_account.id}"
            }, status=status.HTTP_404_NOT_FOUND)

        response = Response({
            'message': 'Kakao Login Callback - Register Success',
            'data': {
                'user_id': accept_json['user']['pk'],
                'username': accept_json['user']['username'],
            },
            'token': {
                'access': token_info['access_token'],
                'refresh': token_info['refresh_token'],
                'access_expire': token_info['at_expires_in'].isoformat(),
                'refresh_expire': token_info['rt_expires_in'].isoformat()
            }
        }, status=status.HTTP_200_OK)

        response.set_cookie(
            key='access',
            value=token_info['access_token'],
            expires=token_info['at_expires_in'].isoformat(),
            max_age=timedelta(minutes=5),
            httponly=True,  # Prevents JavaScript access to the cookie
            secure=True,  # Ensures the cookie is only sent over HTTPS
            samesite='None'
        )

        # Set the 'refresh' token as a cookie
        response.set_cookie(
            key='refresh',
            value=token_info['refresh_token'],
            expires=token_info['rt_expires_in'].isoformat(),
            max_age=timedelta(days=7),
            httponly=True,  # Prevents JavaScript access to the cookie
            secure=True,  # Ensures the cookie is only sent over HTTPS
            samesite='None'
        )

        logger.info(f"Registration process completed successfully for user: {user.id}")
        return response

    except Exception as e:
        logger.error(f"Unexpected error during Kakao callback: {str(e)}", exc_info=True)
        return Response({
            "error": "Kakao Login Callback Fail",
            "detail": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def kakao_refresh_token(request):
    try:
        logger.info("Kakao refresh token request initiated")

        # Check for Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            logger.warning("Authorization header missing in request")
            return Response({
                'error': 'Kakao Refresh Token POST Fail',
                'detail': "Authorization header required to refresh token information"
            },
            status=status.HTTP_400_BAD_REQUEST)

        # Extract and validate token from the Authorization header
        try:
            token_type, refresh_token = auth_header.split()
            if token_type.lower() != 'bearer':
                raise ValueError("Invalid token type")
            logger.debug(f"Authorization header processed: {auth_header}")

        except ValueError as e:
            logger.error(f"Invalid authorization header format: {str(e)}")
            return Response({
                'error': 'Kakao Refresh Token POST Fail',
                'detail': str(e)
            },
            status=status.HTTP_400_BAD_REQUEST)

        # Set up the request to the Kakao API
        kakao_token_uri = "https://kauth.kakao.com/oauth/token"
        request_data = {
            'grant_type': 'refresh_token',
            'client_id': settings.KAKAO_REST_API_KEY,
            'refresh_token': refresh_token,
        }
        token_headers = {
            'Content-type': 'application/x-www-form-urlencoded;charset=utf-8'
        }
        logger.debug(f"Request data prepared for Kakao API: {request_data}")

        # Send the request to the Kakao API to get new tokens
        try:
            token_res = requests.post(
                kakao_token_uri,
                data=request_data,
                headers=token_headers
            )
            logger.debug(f"Kakao API response status: {token_res.status_code}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to make request to Kakao API: {str(e)}", exc_info=True)
            return Response({
                "error": "Kakao Refresh Token POST Fail",
                "detail": f"Failed to make request to Kakao API: {str(e)}"
            }, status=status.HTTP_502_BAD_GATEWAY)

        # Check if the response is successful
        if token_res.status_code not in [200, 201]:
            logger.error(f"Failed to refresh token, response from Kakao: {token_res.text}")
            return Response({
                "error": "Kakao Refresh Token POST Fail",
                "detail": f"Failed to refresh token: {token_res.text}"}, 
                status=token_res.status_code
            )

        token_json = token_res.json()

        access_token = token_json.get('access_token', '')
        refresh_token = token_json.get('refresh_token', '')
        at_expire = token_json.get('expires_in', 0) 
        access_token_expiration = timezone.now() + timedelta(seconds=at_expire)
        refresh_token_expiration = token_json.get('refresh_token_expires_in', 0)
        if refresh_token_expiration:
            refresh_token_expiration = timezone.now() + timedelta(seconds=refresh_token_expiration)
        logger.debug("Token information retrieved from Kakao API")

        # Update the SocialToken
        try:
            social_user = SocialAccount.objects.get(user=request.user)
            social_token = SocialToken.objects.get(account=social_user)

            social_token.token = access_token
            social_token.expires_at = access_token_expiration
            final_refresh_token = refresh_token if refresh_token else social_token.token_secret
            social_token.token_secret = final_refresh_token
            social_token.save()

            logger.info(f"Social token updated for user: {request.user.id}")

        except SocialAccount.DoesNotExist:
            logger.error(f"SocialAccount not found for user ID: {request.user.id}")
            return Response({
                'error': 'Kakao Refresh Token POST Fail',
                'detail': f"SocialAccount not found for user ID: {request.user.id}"
            }, status=status.HTTP_404_NOT_FOUND)

        except SocialToken.DoesNotExist:
            logger.error(f"SocialToken not found for user ID: {request.user.id}")
            return Response({
                'error': 'Kakao Refresh Token POST Fail',
                'detail': f"SocialToken not found for user ID: {request.user.id}"
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error(f"Error occurred while updating the token: {str(e)}", exc_info=True)
            return Response({
                'error': 'Kakao Refresh Token POST Fail',
                'detail': f"An error occurred while updating the token: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Prepare the response with the new token information
        response_data = {
            'message': 'Kakao Token Refresh Success'
        }
        logger.info(f"Token refresh successful for user: {request.user.id}")

        res = Response(response_data, status=status.HTTP_200_OK)

        # Set cookies for access and refresh tokens with new expiration dates
        res.set_cookie(
            key="access",
            value=access_token,
            max_age=None,
            expires=access_token_expiration.isoformat(),
            secure=True,
            samesite=None,
            httponly=True
        )
        res.set_cookie(
            key="refresh",
            value=final_refresh_token,
            max_age=None,
            expires=refresh_token_expiration.isoformat(),
            secure=True,
            samesite=None,
            httponly=True
        )

        # Return the response with updated token information
        return res

    except Exception as e:
        logger.error(f"Unexpected error during Kakao refresh token request: {str(e)}", exc_info=True)
        return Response({
            "error": "Kakao Refresh Token POST Fail",
            "detail": f"An unexpected error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 카카오 계정과 함께 로그아웃? or 서비스만 로그아웃? -> 카카오 로그아웃 선택 페이지 리다이렉트
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def kakao_direct_logout(request):
    return redirect(f'https://kauth.kakao.com/oauth/logout?client_id={settings.KAKAO_REST_API_KEY}&logout_redirect_uri={settings.KAKAO_LOGOUT_REDIRECT_URI}')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def kakao_logout(request):
    try:
        logger.info("Kakao logout request initiated")

        """
        Extract Access Token from the request header
        """
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning("Authorization header missing or invalid in request")
            return Response({
                "error": "Kakao Logout GET Fail",
                "detail": "No access token provided"
            }, status=status.HTTP_401_UNAUTHORIZED)

        access_token = auth_header.split(' ')[1]
        logger.debug(f"Access token extracted: {access_token}")

        """
        Validate the Access Token
        """
        kakao_verify_url = 'https://kapi.kakao.com/v1/user/access_token_info'
        headers = {'Authorization': f'Bearer {access_token}'}
        verify_response = requests.get(kakao_verify_url, headers=headers)

        if verify_response.status_code != 200:
            logger.warning("Invalid or expired access token provided")
            return Response({
                "error": "Kakao Logout GET Fail",
                "detail": "Invalid or expired access token"
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Extract uid from Kakao's response
        kakao_uid = verify_response.json().get('id')
        if not kakao_uid:
            logger.error("Failed to retrieve user ID from Kakao during logout")
            return Response({
                "error": "Kakao Logout GET Fail",
                "detail": "Unable to retrieve user ID from Kakao"
            }, status=status.HTTP_404_NOT_FOUND)
        
        headers = {"Authorization": f'KakaoAK {settings.KAKAO_ADMIN_KEY}'}
        try:
            response = requests.post(
                'https://kapi.kakao.com/v1/user/logout',
                data={
                    'target_id_type': 'user_id',
                    'target_id': kakao_uid
                },
                headers=headers
            )
            logger.debug(f"Logout request sent to Kakao API for user ID: {kakao_uid}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Request to Kakao API failed: {str(e)}", exc_info=True)
            return Response({
                "error": "Kakao Logout GET Fail",
                "detail": f"Request to Kakao API failed : {str(e)}"
            }, status=status.HTTP_502_BAD_GATEWAY)

        if response.status_code != 200:  # (Mostly) Bad Request 400
            logger.error(f"Kakao API responded with an error: {response.json()}")
            return Response({
                'error': "Kakao Logout GET Fail",
                'detail': response.json()
                }, status=response.status_code
            )

        try:
            social_token = SocialToken.objects.get(token=access_token)
            logger.debug(f"SocialToken found for user, proceeding to expire token: {social_token.account.user.id}")
        except SocialToken.DoesNotExist:
            logger.warning("SocialToken does not exist or already expired")
            return Response({
                "error": "Kakao Logout GET Fail",
                "detail": "Invalid or expired access token"
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Expire the token by setting the expiration date to the lowest possible value
        social_token.expires_at = parse_datetime('0001-01-01T00:00:00Z')
        social_token.save()
        logger.info(f"Access token expired successfully for user ID: {social_token.account.user.id}")

        response = Response({
            "message": "Kakao Logout Success (Access Token has been expired)",
        }, status=status.HTTP_200_OK)

        response.delete_cookie('access')
        response.delete_cookie('refresh')
        logger.info("Cookies for access and refresh tokens deleted")

        return response

    except Exception as e:
        logger.error(f"Unexpected error during Kakao logout: {str(e)}", exc_info=True)
        return Response({
            "error": "Kakao Logout GET Fail",
            "detail": f"An unexpected error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def kakao_logout_home_redirect(request):
    try:
        # Retrieve the Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            raise AuthenticationFailed("Authorization header not provided")

        # Split the header into token type and the token itself
        token_type, access_token = auth_header.split()

        # Ensure the token type is Bearer
        if token_type.lower() != 'bearer':
            raise AuthenticationFailed("Invalid token type")

        # Kakao Logout - Admin Key
        # headers = {"Authorization": f'KakaoAK {settings.KAKAO_ADMIN_KEY}'}
        # try:
        #     logout_response = requests.post(
        #         'https://kapi.kakao.com/v1/user/logout',
        #         data={
        #             'target_id_type': 'user_id',
        #             'target_id': target_id
        #         },
        #         headers=headers
        #     )
        # except requests.exceptions.RequestException as e:
        #     return Response({
        #         'error': 'Kakao Logout GET Fail',
        #         'detail': f'Failed to make request to Kakao API: {str(e)}'
        #     }, status=status.HTTP_502_BAD_GATEWAY)

        # Kakao Logout - Access Token
        headers = {"Authorization": f'Bearer {access_token}'}
        try:
            logout_response = requests.post(
                'https://kapi.kakao.com/v1/user/logout',
                headers=headers
            )
        except requests.exceptions.RequestException as e:
            return Response({
                'error': 'Kakao Logout GET Fail',
                'detail': f'Failed to make request to Kakao API: {str(e)}'
            }, status=status.HTTP_502_BAD_GATEWAY)

        # Check Kakao API response
        if logout_response.status_code != 200:
            return Response({
                'error': 'Kakao Logout GET Fail',
                'detail': 'Failed to logout from Kakao'
            }, status=logout_response.status_code)

        return Response({
            'message': 'Kakao Logout Success'
            }, status=status.HTTP_200_OK
            )
    except SocialToken.DoesNotExist:
        raise AuthenticationFailed("Invalid token")    
    except ValueError:
        raise AuthenticationFailed("Invalid Authorization header format")
    except AuthenticationFailed as e:
        return Response({
            'error': 'Kakao Logout GET Fail',
            'detail': 'Authentication Failed : ' + str(e)
        }, status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        return Response({
            "error": "Kakao Logout GET Fail",
            "detail": f"An unexpected error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 카카오 계정 탈퇴
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def kakao_unlink(request):
    try:
        logger.info("Kakao unlink request initiated")

        """
        Extract Access Token from the request header
        """
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning("Authorization header missing or invalid in request")
            return Response({
                "error": "Kakao Unlink GET Fail",
                "detail": "No access token provided"
            }, status=status.HTTP_401_UNAUTHORIZED)

        access_token = auth_header.split(' ')[1]
        logger.debug(f"Access token extracted: {access_token}")

        """
        Validate the Access Token
        """
        kakao_verify_url = 'https://kapi.kakao.com/v1/user/access_token_info'
        headers = {'Authorization': f'Bearer {access_token}'}
        verify_response = requests.get(kakao_verify_url, headers=headers)

        if verify_response.status_code != 200:
            logger.warning("Invalid or expired access token provided")
            return Response({
                "error": "Kakao Unlink GET Fail",
                "detail": "Invalid or expired access token"
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Extract uid from Kakao's response
        kakao_uid = verify_response.json().get('id')
        if not kakao_uid:
            logger.error("Failed to retrieve user ID from Kakao during unlink")
            return Response({
                "error": "Kakao Unlink GET Fail",
                "detail": "Unable to retrieve user ID from Kakao"
            }, status=status.HTTP_404_NOT_FOUND)

        logger.debug(f"Kakao user ID retrieved: {kakao_uid}")

        """
        Check SocialAccount Existence
        """
        try:
            social_account = SocialAccount.objects.get(uid=kakao_uid, provider='kakao')
            user = social_account.user
            logger.debug(f"SocialAccount found for user ID: {user.id}")
        except SocialAccount.DoesNotExist:
            logger.warning(f"No SocialAccount found with uid: {kakao_uid}")
            return Response({
                "error": "Kakao Unlink GET Fail",
                "detail": f"No SocialAccount found with uid: {kakao_uid}"
            }, status=status.HTTP_404_NOT_FOUND)

        """
        Unlink the account from the social provider (KAKAO)
        """
        headers = {"Authorization": f'Bearer {access_token}'}
        try:
            response = requests.post(
                'https://kapi.kakao.com/v1/user/unlink',
                headers=headers
            )
            logger.debug(f"Unlink request sent to Kakao API for user ID: {kakao_uid}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Request to Kakao API failed: {str(e)}", exc_info=True)
            return Response({
                "error": "Kakao Unlink GET Fail",
                "detail": f"Request to Kakao API failed : {str(e)}"
            }, status=status.HTTP_502_BAD_GATEWAY)

        if response.status_code != 200:  # (Mostly) Bad Request 400
            logger.error(f"Kakao API responded with an error: {response.json()}")
            return Response({
                'error': "Kakao Unlink GET Fail",
                'detail': response.json()
                }, status=response.status_code
            )

        logger.info(f"Kakao account unlinked successfully for user ID: {kakao_uid}")

        """
        User Delete (Finalize Unlink)
        """
        try:
            if user:
                user.delete()
                logger.info(f"User and associated SocialAccount deleted successfully for user ID: {kakao_uid}")
                return Response({
                    "message": "User and SocialAccount deletion success",
                    "detail": f"User with uid {kakao_uid} and associated SocialAccount deleted successfully."
                }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            logger.error(f"User with user ID {kakao_uid} does not exist during unlink finalization")
            return Response({
                "error": "Kakao Unlink GET Fail",
                "detail": f"User does not exist."
            }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        logger.error(f"Unexpected error during Kakao unlink: {str(e)}", exc_info=True)
        return Response({
            "error": "Kakao Unlink GET Fail",
            "detail": f"An unexpected error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Proceed with unlinking or further processing
# target_id = user.social_uid

# Unlink from Kakao
# headers = {"Authorization": f'KakaoAK {settings.KAKAO_ADMIN_KEY}'}
# try:
#     response = requests.post(
#         'https://kapi.kakao.com/v1/user/unlink',
#         data={
#             'target_id_type': 'user_id',
#             'target_id': target_id
#         },
#         headers=headers
#     )
# except requests.exceptions.RequestException as e:
#     return Response({
#         "error": "Kakao Unlink GET Fail",
#         "detail": f"Request to Kakao API failed : {str(e)}"
#     }, status=status.HTTP_502_BAD_GATEWAY)

@api_view(['GET'])
def kakao_show_verified(request):
    try:
        logger.info("Kakao account verification request initiated")

        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning("Authorization header missing or invalid in request")
            return Response({
                "error": "Kakao Show Verified GET Fail",
                "detail": "No access token provided"
            }, status=status.HTTP_401_UNAUTHORIZED)

        access_token = auth_header.split(' ')[1]
        logger.debug(f"Access token extracted: {access_token}")

        try:
            social_token = SocialToken.objects.get(token=access_token)
            logger.debug(f"SocialToken found for access token: {access_token}")
        except SocialToken.DoesNotExist:
            logger.warning(f"SocialToken does not exist for the provided access token: {access_token}")
            return Response({
                'error': 'Kakao Show Verified GET Fail',
                'detail': 'Invalid Token or token does not exist'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check authenticated user (Access Token Expiration)
        if social_token.expires_at and social_token.expires_at < timezone.now():
            logger.warning(f"Access token has expired for token: {access_token}")
            return Response({
                'error': 'Kakao Show Verified GET Fail',
                'detail': 'Invalid Token or token does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=social_token.account_id)
            logger.debug(f"User found for account ID: {social_token.account_id}")
        except User.DoesNotExist:
            logger.warning(f"Requested user does not exist for account ID: {social_token.account_id}")
            return Response({
                'error': 'Kakao Show Verified GET Fail',
                'detail': 'Requested user does not exist'
            }, status=status.HTTP_404_NOT_FOUND)

        logger.info(f"Kakao account verification successful for user: {user.username}")
        return Response({
            'message': 'Kakao Account Verification Success',
            'data': {'username': user.username}
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Unexpected error during Kakao account verification: {str(e)}", exc_info=True)
        return Response({
            "error": "Kakao Show Verified GET Fail",
            "detail": f"An unexpected error occurred: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
class KakaoLoginView(SocialLoginView):
    adapter_class = KakaoOAuth2Adapter
    callback_url = f"{settings.KAKAO_LOGIN_CALLBACK_URI}"
    client_class = OAuth2Client