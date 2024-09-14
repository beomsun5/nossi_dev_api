from rest_framework.views import APIView
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.db.models import OuterRef, Subquery
from django.http import Http404
from ..models import *
from ..serializers import *
from allauth.socialaccount.models import SocialAccount, SocialToken
import logging 

# Get the logger instance for the 'rest' application
logger = logging.getLogger('rest')

# user-profile
class UserProfileView(APIView):
    # Not API, just method
    def get_object(self, user_id):
        try:
            return Profile.objects.get(user_id=user_id)
        except Profile.DoesNotExist:
            raise Http404("Profile not found")
        except Exception as e:
            raise e

    @permission_classes([IsAuthenticated])
    def get(self, request):
        try:
            logger.info("User profile GET request initiated")

            # Check for Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                logger.warning("Authorization header missing or invalid in request")
                return Response({
                    "error": "User Profile GET Fail",
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
                    "error": "User Profile GET Fail",
                    "detail": "Invalid or expired access token"
                }, status=status.HTTP_401_UNAUTHORIZED)

            profile = self.get_object(social_token.account_id)
            logger.info(f"Profile retrieved for account ID: {social_token.account_id}")

            # Serialize the profile, excluding the user_id field
            profile_serializer = ProfileSerializer(profile)
            data = profile_serializer.data
            data.pop('user_id', None)  # Exclude user_id from the serialized data

            logger.info(f"User profile serialization successful for account ID: {social_token.account_id}")
            return Response({
                'message': 'User Profile Retrieval Success',
                'data': data
            }, status=status.HTTP_200_OK)

        except Http404 as e:
            logger.warning(f"User profile not found: {str(e)}")
            return Response({
                'error': 'User Profile GET Fail',
                'detail': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            logger.error(f"Unexpected error during profile retrieval: {str(e)}", exc_info=True)
            return Response({
                'error': 'User Profile GET Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @permission_classes([IsAuthenticated])
    def put(self, request):
        try:
            logger.info("User profile update request initiated")

            # Check for Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                logger.warning("Authorization header missing or invalid in request")
                return Response({
                    "error": "User Profile Update Fail",
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
                    "error": "User Profile Update Fail",
                    "detail": "Invalid or expired access token"
                }, status=status.HTTP_401_UNAUTHORIZED)

            profile = self.get_object(social_token.account_id)
            logger.info(f"Profile retrieved for account ID: {social_token.account_id}")

            profile_serializer = ProfileSerializer(profile, data=request.data)
            if profile_serializer.is_valid():
                profile_serializer.save()
                logger.info(f"User profile updated successfully for account ID: {social_token.account_id}")
                return Response({
                    'message': 'User Profile Update Success',
                    'data': profile_serializer.data
                }, status=status.HTTP_200_OK)
            
            logger.warning(f"User profile update failed validation for account ID: {social_token.account_id}")
            return Response({
                'error': 'User Profile PUT Fail',
                'detail': profile_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        except Http404 as e:
            logger.warning(f"User profile not found: {str(e)}")
            return Response({
                'error': 'User Profile PUT Fail',
                'detail': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            logger.error(f"Unexpected error during profile update: {str(e)}", exc_info=True)
            return Response({
                'error': 'User Profile PUT Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @permission_classes([IsAuthenticated])
    def patch(self, request):
        try:
            logger.info("User profile partial update request initiated")

            # Check for Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                logger.warning("Authorization header missing or invalid in request")
                return Response({
                    "error": "User Profile Partial Update Fail",
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
                    "error": "User Profile Partial Update Fail",
                    "detail": "Invalid or expired access token"
                }, status=status.HTTP_401_UNAUTHORIZED)

            profile = self.get_object(social_token.account_id)
            logger.info(f"Profile retrieved for account ID: {social_token.account_id}")

            profile_serializer = ProfileSerializer(profile, data=request.data, partial=True)
            if profile_serializer.is_valid():
                profile_serializer.save()
                logger.info(f"User profile partially updated successfully for account ID: {social_token.account_id}")
                return Response({
                    'message': 'User Profile Partial Update Success',
                    'data': profile_serializer.data
                }, status=status.HTTP_200_OK)
            
            logger.warning(f"User profile partial update failed validation for account ID: {social_token.account_id}")
            return Response({
                'error': 'User Profile PATCH Fail',
                'detail': profile_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        except Http404 as e:
            logger.warning(f"User profile not found: {str(e)}")
            return Response({
                'error': 'User Profile PATCH Fail',
                'detail': str(e)
            }, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            logger.error(f"Unexpected error during profile partial update: {str(e)}", exc_info=True)
            return Response({
                'error': 'User Profile PATCH Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UserSubmissionView(APIView):
    @permission_classes([IsAuthenticated])
    def get(self, request):
        try:
            logger.info("User submission retrieval request initiated")

            # Check for Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                logger.warning("Authorization header missing or invalid in request")
                return Response({
                    "error": "User Submission GET Fail",
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
                    "error": "User Submission GET Fail",
                    "detail": "Invalid or expired access token"
                }, status=status.HTTP_401_UNAUTHORIZED)

            user_id = social_token.account_id
            logger.info(f"Retrieving submissions for user ID: {user_id}")

            # Retrieve the latest submission for each problem attempted by the user
            latest_submissions = Submission.objects.filter(
                user_id=user_id,
                problem_id=OuterRef('problem_id')
            ).order_by('-submitted_at')

            submissions = Submission.objects.filter(
                user_id=user_id,
                id=Subquery(latest_submissions.values('id')[:1])
            ).select_related('problem_id').values(
                'problem_id__title', 
                'final_result', 
                'submitted_at'
            ).order_by('-submitted_at')

            submission_count = len(submissions)
            logger.info(f"Submissions retrieved successfully for user ID: {user_id} ({submission_count} submission(s) found)")

            # Construct the final response
            submission_data = [
                {
                    'title': submission['problem_id__title'],
                    'final_result': submission['final_result'],
                    'submitted_at': submission['submitted_at']
                }
                for submission in submissions
            ]

            return Response({
                'message': f'User Submission Retrieval Success : {submission_count} submission(s) found',
                'data': submission_data
            }, status=status.HTTP_200_OK)

        except DatabaseError as db_err:
            logger.error(f"Database error during submission retrieval for user ID: {user_id}, error: {str(db_err)}", exc_info=True)
            return Response({
                'error': 'User Submission GET Fail',
                'detail': 'A database error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Unexpected error during submission retrieval for user ID: {user_id}, error: {str(e)}", exc_info=True)
            return Response({
                'error': 'User Submission GET Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)