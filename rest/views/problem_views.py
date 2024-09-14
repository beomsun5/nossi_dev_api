from django.utils import timezone
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from django.db.models import F
from django_redis import get_redis_connection
from django_ratelimit.decorators import ratelimit
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from ..tasks import do_judge_for_task, create_submission_and_response_for_task
from ..models import *
from ..serializers import *
from .zip_extraction import *
from ..utils import *
from .code_judge.Judger import SubmissionDriver, Compiler, Judger
from .code_judge.config import lang_config, RUN_BASE_DIR, TESTCASE_BASE_DIR
from allauth.socialaccount.models import SocialAccount, SocialToken
from celery.result import AsyncResult
from pathlib import Path
import os
import logging


# Get the logger instance for the 'rest' application
logger = logging.getLogger('rest')

SUBMISSION_RESULT = {
    -2: "SOLVED",
    -1: "WRONG",
    1: "TIME_LIMIT_EXCEEDED",
    2: "TIME_LIMIT_EXCEEDED",
    3: "MEMORY_LIMIT_EXCEEDED",
    4: "RUNTIME_ERROR",
    5: "SYSTEM_ERROR",
}

"""
[다수 문제 데이터 다루기 & 새로운 데이터 추가하기]
"""
# problem-list
class ProblemListView(APIView):

    def get(self, request):
        try:
            logger.info("Problem list retrieval request initiated")

            user_id = None
            # Check for Authorization header
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                access_token = auth_header.split(' ')[1]
                logger.debug(f"Access token extracted: {access_token}")
                
                try:
                    social_token = SocialToken.objects.get(token=access_token)
                    logger.debug(f"SocialToken found for access token: {access_token}")
                    # Check authenticated user (Access Token Expiration)
                    if social_token.expires_at and social_token.expires_at < timezone.now():
                        logger.warning("Access token has expired")
                        user_id = None
                    else:
                        user_id = social_token.account_id
                except SocialToken.DoesNotExist:
                    logger.warning(f"SocialToken does not exist for the provided access token: {access_token}")

            # Cache key for the problem list, based on user authentication status
            cache_key = generate_problem_list_cache_key(user_id)
            cached_data = cache.get(cache_key)

            if cached_data:
                logger.info("Returning cached problem list")
                return Response({
                    'message': f'Problem List Retrieval Success - {len(cached_data)} problem(s) found (cached)',
                    'data': cached_data
                }, status=status.HTTP_200_OK)

            # Retrieve the list of problems ordered by the updated_at field
            problems = Problem.objects.all().order_by('-updated_at')
            logger.info(f"{problems.count()} problem(s) retrieved")

            if not problems.exists():
                logger.info("No problems found")
                return Response({
                    'message': 'Problem List Retrieval Success - 0 problem(s) found',
                    'data': []
                }, status=status.HTTP_200_OK)

            # Serialize the problems
            problem_serializer = ProblemSerializer(problems, many=True, context={'user_id': user_id, 'request': request})
            logger.info(f"Problem list serialized successfully with {len(problem_serializer.data)} problem(s)")

            # Cache the serialized data for future requests
            cache.set(cache_key, problem_serializer.data, timeout=600)  # Cache for 10 minutes

            # Track user_id in Redis for future cache invalidation
            redis_conn = get_redis_connection("default")
            if user_id:
                redis_conn.sadd("cached_users", user_id)  # Add user_id to the Redis set

            # Return the serialized data
            return Response({
                'message': f'Problem List Retrieval Success - {len(problem_serializer.data)} problem(s) found',
                'data': problem_serializer.data
            }, status=status.HTTP_200_OK)

        except ValidationError as ve:
            logger.warning(f"Validation error during problem list serialization: {ve.message_dict}")
            return Response({
                'error': 'Problem List GET Fail',
                'detail': f'Validation error occurred during serialization: {ve.message_dict}',
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error during problem list retrieval: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem List GET Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request):
        try:
            logger.info("New problem addition request initiated")

            problem_meta_data = request.data.pop('problem_meta', None)
            problem_serializer = ProblemSerializer(data=request.data)

            if problem_serializer.is_valid():
                problem = problem_serializer.save()
                logger.info(f"New problem created successfully with ID: {problem.id}")

                if problem_meta_data:
                    problem_meta_data['problem_id'] = problem.id
                    problem_meta_serializer = ProblemMetaSerializer(data=problem_meta_data)

                    if problem_meta_serializer.is_valid():
                        problem_meta_serializer.save()
                        logger.info(f"Problem metadata saved successfully for problem ID: {problem.id}")
                    else:
                        problem.delete()
                        logger.warning(f"ProblemMeta validation failed, problem ID {problem.id} deleted: {problem_meta_serializer.errors}")
                        return Response({
                            'error': 'Problem List POST Fail',
                            'detail': f'ProblemMeta Validation Fail: {problem_meta_serializer.errors}'
                        }, status=status.HTTP_400_BAD_REQUEST)
                
                # Prepare the response data
                response_data = problem_serializer.data
                response_data['problem_meta'] = problem_meta_serializer.data

                logger.info(f"Problem addition completed successfully for problem ID: {problem.id}")
                return Response({
                    'message': 'New Problem Addition Success',
                    'data': response_data
                }, status=status.HTTP_201_CREATED)

            logger.warning(f"Problem validation failed: {problem_serializer.errors}")
            return Response({
                'error': 'Problem List POST Fail',
                'detail': problem_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        except ValidationError as ve:
            logger.warning(f"Validation error during problem addition: {ve.message_dict}")
            return Response({
                'error': 'Problem List POST Fail',
                'detail': f'Validation error occurred during data processing: {ve.message_dict}',
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Unexpected error during problem addition: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem List POST Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

"""
[한 문제 데이터 다루기]
"""
# problem-detail
class ProblemDetailView(APIView):

    def get(self, request, problem_id):
        try:
            logger.info(f"Problem detail retrieval request initiated for problem ID: {problem_id}")

            # Generate a single cache key for the combined Problem and ProblemMeta data
            cache_key = generate_problem_cache_key(problem_id)
            cached_data = cache.get(cache_key)

            if cached_data:
                logger.info(f"Returning cached data for problem ID {problem_id}")
                return Response({
                    'message': 'Problem Retrieval Success (cached)',
                    'data': cached_data
                }, status=status.HTTP_200_OK)

            problem = Problem.objects.get(id=problem_id)
            problem_serializer = ProblemSerializer(problem, context={'request': request})
            logger.debug(f"Problem with ID {problem_id} retrieved successfully")

            problem_meta = ProblemMeta.objects.get(problem_id=problem_id)
            problem_meta_serializer = ProblemMetaSerializer(problem_meta)
            logger.debug(f"ProblemMeta for problem ID {problem_id} retrieved successfully")

            # Combine the serialized data
            response_data = problem_serializer.data
            response_data['problem_meta'] = problem_meta_serializer.data

            # Cache the combined data for future requests (cache for 10 minutes)
            cache.set(cache_key, response_data, timeout=600)
            logger.info(f"Problem detail cached successfully for problem ID {problem_id}")

            logger.info(f"Problem detail retrieval successful for problem ID: {problem_id}")
            return Response({
                'message': 'Problem Retrieval Success',
                'data': response_data
            }, status=status.HTTP_200_OK)

        except Problem.DoesNotExist:
            logger.warning(f"Problem with ID {problem_id} not found")
            return Response({
                'error': 'Problem Detail GET Fail',
                'detail': f'Problem with ID {problem_id} is not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except ProblemMeta.DoesNotExist:
            logger.warning(f"ProblemMeta for problem ID {problem_id} not found")
            return Response({
                'error': 'Problem Detail GET Fail',
                'detail': f'ProblemMeta for problem {problem_id} is not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Unexpected error during problem detail retrieval for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Detail GET Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, problem_id):
        try:
            logger.info(f"Problem detail update request initiated for problem ID: {problem_id}")

            try:
                problem = Problem.objects.get(id=problem_id)
                logger.debug(f"Problem with ID {problem_id} retrieved successfully for update")
            except Problem.DoesNotExist:
                logger.warning(f"Problem with ID {problem_id} not found for update")
                return Response({
                    'error': 'Problem Detail PUT Fail',
                    'detail': f'Problem with ID {problem_id} is not found'
                }, status=status.HTTP_404_NOT_FOUND)

            problem_meta_data = request.data.pop('problem_meta', None)
            problem_serializer = ProblemSerializer(problem, data=request.data, context={'request': request})

            if problem_serializer.is_valid():
                problem_serializer.save()
                logger.info(f"Problem with ID {problem_id} updated successfully")

                if problem_meta_data:
                    try:
                        problem_meta = ProblemMeta.objects.get(problem_id=problem_id)
                        problem_meta_data['problem_id'] = problem_id
                        problem_meta_serializer = ProblemMetaSerializer(problem_meta, data=problem_meta_data)
                        if problem_meta_serializer.is_valid():
                            problem_meta_serializer.save()
                            logger.info(f"ProblemMeta updated successfully for problem ID: {problem_id}")
                        else:
                            logger.warning(f"ProblemMeta validation failed for problem ID {problem_id}: {problem_meta_serializer.errors}")
                            return Response({
                                'error': 'Problem Detail PUT Fail',
                                'detail': problem_meta_serializer.errors
                            }, status=status.HTTP_400_BAD_REQUEST)
                    except ProblemMeta.DoesNotExist:
                        logger.warning(f"ProblemMeta not found for problem ID {problem_id} during update")
                        return Response({
                            'error': 'Problem Detail PUT Fail',
                            'detail': f'ProblemMeta for problem {problem_id} is not found'
                        }, status=status.HTTP_404_NOT_FOUND)

                response_data = problem_serializer.data
                response_data['problem_meta'] = problem_meta_serializer.data if problem_meta_data else {}

                logger.info(f"Problem and ProblemMeta update successful for problem ID: {problem_id}")
                return Response({
                    'message': 'Problem Update Success',
                    'data': response_data
                }, status=status.HTTP_200_OK)
            
            logger.warning(f"Problem validation failed for problem ID {problem_id}: {problem_serializer.errors}")
            return Response({
                'error': 'Problem Detail PUT Fail',
                'detail': problem_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Unexpected error during problem update for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Detail PUT Fail',
                'detail': f'An unexpected error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, problem_id):
        try:
            logger.info(f"Problem partial update request initiated for problem ID: {problem_id}")

            try:
                problem = Problem.objects.get(id=problem_id)
                logger.debug(f"Problem with ID {problem_id} retrieved successfully for partial update")
            except Problem.DoesNotExist:
                logger.warning(f"Problem with ID {problem_id} not found for partial update")
                return Response({
                    'error': 'Problem Detail PATCH Fail',
                    'detail': f'Problem with ID {problem_id} is not found'
                }, status=status.HTTP_404_NOT_FOUND)

            problem_meta_data = request.data.pop('problem_meta', None)
            problem_serializer = ProblemSerializer(problem, data=request.data, context={'request': request}, partial=True)

            if problem_serializer.is_valid():
                problem_serializer.save()
                logger.info(f"Problem with ID {problem_id} partially updated successfully")

                if problem_meta_data:
                    try:
                        problem_meta = ProblemMeta.objects.get(problem_id=problem_id)
                        problem_meta_serializer = ProblemMetaSerializer(problem_meta, data=problem_meta_data, partial=True)
                        if problem_meta_serializer.is_valid():
                            problem_meta_serializer.save()
                            logger.info(f"ProblemMeta partially updated successfully for problem ID: {problem_id}")
                        else:
                            logger.warning(f"ProblemMeta validation failed for problem ID {problem_id}: {problem_meta_serializer.errors}")
                            return Response({
                                'error': 'ProblemMeta PATCH Fail',
                                'detail': problem_meta_serializer.errors
                            }, status=status.HTTP_400_BAD_REQUEST)
                    except ProblemMeta.DoesNotExist:
                        logger.warning(f"ProblemMeta not found for problem ID {problem_id} during partial update")
                        return Response({
                            'error': 'ProblemMeta PATCH Fail',
                            'detail': f'ProblemMeta for problem {problem_id} is not found'
                        }, status=status.HTTP_404_NOT_FOUND)

                response_data = problem_serializer.data
                response_data['problem_meta'] = problem_meta_serializer.data if problem_meta_data else {}

                logger.info(f"Problem and ProblemMeta partial update successful for problem ID: {problem_id}")
                return Response({
                    'message': 'Problem Partial Update Success',
                    'data': response_data
                }, status=status.HTTP_200_OK)

            logger.warning(f"Problem validation failed for problem ID {problem_id}: {problem_serializer.errors}")
            return Response({
                'error': 'Problem Detail PATCH Fail',
                'detail': problem_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Unexpected error during problem partial update for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Detail PATCH Fail',
                'detail': f'An unexpected error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, problem_id):
        try:
            logger.info(f"Problem deletion request initiated for problem ID: {problem_id}")

            try:
                problem = Problem.objects.get(id=problem_id)
                logger.debug(f"Problem with ID {problem_id} retrieved successfully for deletion")
            except Problem.DoesNotExist:
                logger.warning(f"Problem with ID {problem_id} not found for deletion")
                return Response({
                    'error': 'Problem Detail DELETE Fail',
                    'detail': f'Problem with ID {problem_id} is not found'
                }, status=status.HTTP_404_NOT_FOUND)

            try:
                problem_meta = ProblemMeta.objects.get(problem_id=problem_id)
                problem_meta.delete()
                logger.debug(f"ProblemMeta with problem ID {problem_id} deleted successfully")
            except ProblemMeta.DoesNotExist:
                logger.warning(f"ProblemMeta not found for problem ID {problem_id} during deletion")
                return Response({
                    'error': 'Problem Detail DELETE Fail',
                    'detail': f'ProblemMeta for problem {problem_id} is not found'
                }, status=status.HTTP_404_NOT_FOUND)

            problem.delete()
            logger.info(f"Problem with ID {problem_id} deleted successfully")
            return Response({
                'message': 'Problem Detail DELETE Success'
                },
                status=status.HTTP_204_NO_CONTENT
            )

        except Exception as e:
            logger.error(f"Unexpected error during problem deletion for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Detail DELETE Fail',
                'detail': f'An unexpected error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

"""
[템플릿 코드 및 실행 코드 다루기]
"""
# problem-lang-code
class ProblemLangCodeView(APIView):

    def get(self, request, problem_id):
        try:
            logger.info(f"Problem language code retrieval request initiated for problem ID: {problem_id}")

            language_id = request.query_params.get('language_id')
            if not language_id:
                logger.warning("language_id query parameter missing in GET request")
                return Response({
                    'error': 'Problem Language Code GET Fail',
                    'detail': 'language_id is required as a query parameter'
                }, status=status.HTTP_400_BAD_REQUEST)

            problem_instance = Language.objects.get(id=problem_id)
            if problem_instance is None:
                logger.warning(f"Problem matching problem_id {problem_id} does not exist in DB")
                return Response({
                    'error': 'Problem Language Code GET Fail',
                    'detail': f"Problem matching problem_id {problem_id} does not exist in DB"
                }, status=status.HTTP_400_BAD_REQUEST)

            language_instance = Language.objects.get(id=language_id)
            if language_instance is None:
                logger.warning(f"Language matching language_id {language_id} does not exist in DB")
                return Response({
                    'error': 'Problem Language Code GET Fail',
                    'detail': f"Language matching language_id {language_id} does not exist in DB"
                }, status=status.HTTP_400_BAD_REQUEST)

            init_code = InitCode.objects.filter(problem_id=problem_id, language_id=language_id).first()
            if not init_code:
                logger.warning(f"Code template not found for problem ID {problem_id} and language ID {language_id}")
                return Response({
                    'error': 'Problem Language Code GET Fail',
                    'detail': 'Code template for the problem does not exist in DB'
                }, status=status.HTTP_404_NOT_FOUND)

            init_code_serializer = InitCodeSerializer(init_code)
            logger.info(f"Problem language code retrieval successful for problem ID {problem_id} and language ID {language_id}")
            return Response({
                'message': 'Problem Language Code Retrieval Success',
                'data': init_code_serializer.data
            }, status=status.HTTP_200_OK)

        except ValidationError as e:
            logger.warning(f"Validation error during language code retrieval for problem ID {problem_id}: {str(e)}")
            return Response({
                'error': 'Problem Language Code GET Fail',
                'detail': f'Invalid data: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error during language code retrieval for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Language Code GET Fail',
                'detail': f'An unexpected error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, problem_id):
        try:
            logger.info(f"Problem language code addition request initiated for problem ID: {problem_id}")

            language_id = request.query_params.get('language_id')
            if not language_id:
                logger.warning("language_id query parameter missing in POST request")
                return Response({
                    'error': 'Problem Language Code POST Fail',
                    'detail': 'language_id is required as a query parameter'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Validate that the provided language_id exists
            try:
                language = Language.objects.get(id=language_id)
                logger.debug(f"Language with ID {language_id} found")
            except Language.DoesNotExist:
                logger.warning(f"Language with ID {language_id} not found in POST request")
                return Response({
                    'error': 'Problem Language Code POST Fail',
                    'detail': f'Language with id {language_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            request.data['problem_id'] = problem_id
            request.data['language_id'] = language_id
            
            init_code_serializer = InitCodeSerializer(data=request.data)
            if init_code_serializer.is_valid():
                init_code_serializer.save()
                logger.info(f"Problem language code added successfully for problem ID {problem_id} and language ID {language_id}")
                return Response({
                    'message': 'New Problem Language Code Addition Success',
                    'data': init_code_serializer.data
                }, status=status.HTTP_201_CREATED)
            
            logger.warning(f"Problem language code validation failed for problem ID {problem_id}: {init_code_serializer.errors}")
            return Response({
                'error': 'Problem Language Code POST Fail',
                'detail': init_code_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as ve:
            logger.warning(f"Validation error during language code addition for problem ID {problem_id}: {str(ve)}")
            return Response({
                'error': 'Problem Language Code POST Fail',
                'detail': f'Invalid data: {str(ve)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error during language code addition for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Language Code POST Fail',
                'detail': f'An unexpected error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, problem_id):
        try:
            logger.info(f"Problem language code update request initiated for problem ID: {problem_id}")

            language_id = request.query_params.get('language_id')
            if not language_id:
                logger.warning("language_id query parameter missing in PUT request")
                return Response({
                    'error': 'Problem Language Code PUT Fail',
                    'detail': 'language_id is required as a query parameter'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate that the provided language_id exists
            try:
                language = Language.objects.get(id=language_id)
                logger.debug(f"Language with ID {language_id} found")
            except Language.DoesNotExist:
                logger.warning(f"Language with ID {language_id} not found in PUT request")
                return Response({
                    'error': 'Problem Language Code PUT Fail',
                    'detail': f'Language with id {language_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            init_code = InitCode.objects.filter(problem_id=problem_id, language_id=language_id).first()
            if not init_code:
                logger.warning(f"Code template not found for problem ID {problem_id} and language ID {language_id}")
                return Response({
                    'error': 'Problem Language Code PUT Fail',
                    'detail': 'Code template for the problem does not exist in DB'
                }, status=status.HTTP_404_NOT_FOUND)

            request.data['problem_id'] = problem_id
            request.data['language_id'] = language_id

            init_code_serializer = InitCodeSerializer(init_code, data=request.data)
            if init_code_serializer.is_valid():
                init_code_serializer.save()
                logger.info(f"Problem language code updated successfully for problem ID {problem_id} and language ID {language_id}")
                return Response({
                    'message': 'Problem Language Code Update Success',
                    'data': init_code_serializer.data
                }, status=status.HTTP_200_OK)
            
            logger.warning(f"Problem language code validation failed for problem ID {problem_id}: {init_code_serializer.errors}")
            return Response({
                'error': 'Problem Language Code PUT Fail',
                'detail': init_code_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        except ValidationError as ve:
            logger.warning(f"Validation error during language code update for problem ID {problem_id}: {str(ve)}")
            return Response({
                'error': 'Problem Language Code PUT Fail',
                'detail': f'Invalid data: {str(ve)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error during language code update for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Language Code PUT Fail',
                'detail': f'An unexpected error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, problem_id):
        try:
            logger.info(f"Problem language code partial update request initiated for problem ID: {problem_id}")

            language_id = request.query_params.get('language_id')
            if not language_id:
                logger.warning("language_id query parameter missing in PATCH request")
                return Response({
                    'error': 'Problem Language Code PATCH Fail',
                    'detail': 'language_id is required as a query parameter'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Validate that the provided language_id exists
            try:
                language = Language.objects.get(id=language_id)
                logger.debug(f"Language with ID {language_id} found")
            except Language.DoesNotExist:
                logger.warning(f"Language with ID {language_id} not found in PATCH request")
                return Response({
                    'error': 'Problem Language Code PATCH Fail',
                    'detail': f'Language with id {language_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            init_code = InitCode.objects.filter(problem_id=problem_id, language_id=language_id).first()
            if not init_code:
                logger.warning(f"Code template not found for problem ID {problem_id} and language ID {language_id}")
                return Response({
                    'error': 'Problem Language Code PATCH Fail',
                    'detail': 'Code template for the problem does not exist in DB'
                }, status=status.HTTP_404_NOT_FOUND)

            init_code_serializer = InitCodeSerializer(init_code, data=request.data, partial=True)
            if init_code_serializer.is_valid():
                init_code_serializer.save()
                logger.info(f"Problem language code partially updated successfully for problem ID {problem_id} and language ID {language_id}")
                return Response({
                    'message': 'Problem Language Code Partial Update Success',
                    'data': init_code_serializer.data
                }, status=status.HTTP_200_OK)
            
            logger.warning(f"Problem language code validation failed for problem ID {problem_id}: {init_code_serializer.errors}")
            return Response({
                'error': 'Problem Language Code PATCH Fail',
                'detail': init_code_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        except ValidationError as ve:
            logger.warning(f"Validation error during language code partial update for problem ID {problem_id}: {str(ve)}")
            return Response({
                'error': 'Problem Language Code PATCH Fail',
                'detail': f'Invalid data: {str(ve)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error during language code partial update for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Language Code PATCH Fail',
                'detail': f'An unexpected error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, problem_id):
        try:
            logger.info(f"Problem language code deletion request initiated for problem ID: {problem_id}")

            language_id = request.query_params.get('language_id')
            if not language_id:
                logger.warning("language_id query parameter missing in DELETE request")
                return Response({
                    'error': 'Problem Language Code DELETE Fail',
                    'detail': 'language_id is required as a query parameter'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Validate that the provided language_id exists
            try:
                language = Language.objects.get(id=language_id)
                logger.debug(f"Language with ID {language_id} found")
            except Language.DoesNotExist:
                logger.warning(f"Language with ID {language_id} not found in DELETE request")
                return Response({
                    'error': 'Problem Language Code DELETE Fail',
                    'detail': f'Language with id {language_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            init_code = InitCode.objects.filter(problem_id=problem_id, language_id=language_id).first()
            if not init_code:
                logger.warning(f"Code template not found for problem ID {problem_id} and language ID {language_id}")
                return Response({
                    'error': 'Problem Language Code DELETE Fail',
                    'detail': 'Code template for the problem does not exist in DB'
                }, status=status.HTTP_404_NOT_FOUND)

            init_code.delete()
            logger.info(f"Problem language code deleted successfully for problem ID {problem_id} and language ID {language_id}")
            return Response({
                'message': 'Problem Language Code DELETE Success'
            }, status=status.HTTP_204_NO_CONTENT)

        except ValidationError as ve:
            logger.warning(f"Validation error during language code deletion for problem ID {problem_id}: {str(ve)}")
            return Response({
                'error': 'Problem Language Code DELETE Fail',
                'detail': f'Invalid data: {str(ve)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error during language code deletion for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Language Code DELETE Fail',
                'detail': f'An unexpected error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

"""
[테스트케이스 다루기]
"""
# problem-testcase
class ProblemTestcaseView(APIView):
    # Save testcase
    def post(self, request, problem_id):
        logger.info(f"Problem testcase upload initiated for problem ID: {problem_id}")
        
        testcase_type = request.query_params.get('testcase_type')
        if not testcase_type:
            logger.warning("testcase_type query parameter missing in POST request")
            return Response({
                'error': 'Problem Testcase POST Fail',
                'detail': 'testcase_type query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Ensure that testcase_type starts with an underscore
        if not testcase_type.startswith('_'):
            logger.warning("Invalid testcase_type: does not start with an underscore (_)")
            return Response({
                'error': 'Problem Testcase POST Fail',
                'detail': 'Invalid testcase_type: it must start with an underscore (_).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_serializer = ZipFileUploadSerializer(data=request.data)
        if file_serializer.is_valid():
            try:
                # Get the problem name : Definitely unique
                title = Problem.objects.values_list('title', flat=True).get(pk=problem_id)
                logger.debug(f"Problem with ID {problem_id} found, title: {title}")

                # testcase_dir_name : Generate the directory name for storing test cases
                testcase_dir_name = title.strip().lower().replace(" ", "_") + testcase_type

                # Extract the zip file from the request
                zip_file = request.FILES.get('testcase_zip')
                if not zip_file:
                    logger.warning("testcase_zip file missing in POST request")
                    return Response({
                        'error': 'Problem Testcase POST Fail',
                        'detail': 'testcase_zip file is required'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Create extraction path
                extract_path = Path(TESTCASE_BASE_DIR) / testcase_dir_name
                if not extract_path.exists():
                    extract_path.mkdir(parents=True, exist_ok=True)
                
                zip_file_path = Path(extract_path) / zip_file.name

                # Save the uploaded zip file
                with open(zip_file_path, 'wb') as f:
                    for chunk in zip_file.chunks():
                        f.write(chunk)
                
                logger.debug(f"Zip file saved successfully at {zip_file_path}")

                # 1. extract_zip : Extract the zip file at the extraction path
                extract_zip(zip_file_path, extract_path)
                logger.debug(f"Zip file extracted successfully at {extract_path}")

                # 2. collect_file_info : Organize the contents of the zip file
                data = collect_file_info(extract_path)

                # 3. save_to_json : Save the result of step 2 as info.json
                info_json_path = extract_path / 'info.json'
                save_to_json(data, info_json_path)
                logger.debug(f"File information saved as JSON at {info_json_path}")

                zip_file_path.unlink()  # Remove the zip file
                logger.info(f"Problem testcase upload and processing successful for problem ID {problem_id}")

                # Compose the response
                response_data = {
                    'message': 'Testcase File Save Success',
                    'testcase_name': testcase_dir_name,
                    'extracted_files': data.get('testcase_number', 0),
                }
                return Response(response_data, status=status.HTTP_201_CREATED)

            except Problem.DoesNotExist:
                logger.warning(f"Problem with ID {problem_id} not found in POST request")
                return Response({
                    'error': 'Problem Testcase POST Fail',
                    'detail': f'Problem with ID {problem_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            except zipfile.BadZipFile:
                logger.warning("Uploaded file is not a valid zip file")
                return Response({
                    'error': 'Problem Testcase POST Fail',
                    'detail': 'Uploaded file is not a valid zip file'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except IOError as io_error:
                logger.error(f"File I/O error occurred during POST request: {str(io_error)}", exc_info=True)
                return Response({
                    'error': 'Problem Testcase POST Fail',
                    'detail': f'File I/O error occurred: {str(io_error)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            except Exception as e:
                logger.error(f"Unexpected error during POST request for problem ID {problem_id}: {str(e)}", exc_info=True)
                return Response({
                    'error': 'Problem Testcase POST Fail',
                    'detail': f'An unexpected error occurred: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            logger.warning("Invalid file type provided, expected a zip file")
            return Response({
                'error': 'Problem Testcase POST Fail',
                'detail': 'Invalid file type, expected a zip file'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
    # Load testcase
    def get(self, request, problem_id):
        logger.info(f"Problem testcase retrieval initiated for problem ID: {problem_id}")

        testcase_type = request.query_params.get('testcase_type')
        if not testcase_type or testcase_type not in {'_run', '_submit'}:
            logger.warning("testcase_type query parameter missing or invalid in GET request")
            return Response({
                'error': 'Problem Testcase GET Fail',
                'detail': 'testcase_type query parameter is required and must be either _run or _submit'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            # Retrieve and process the problem title
            title = Problem.objects.values_list('title', flat=True).get(pk=problem_id)
            logger.debug(f"Problem with ID {problem_id} found, title: {title}")

            # Directory path based on testcase_type
            directory_path = Path(TESTCASE_BASE_DIR) / (title.strip().lower().replace(" ", "_") + testcase_type)

            if not directory_path.exists():
                logger.warning(f"Testcase directory not found for problem ID {problem_id} and testcase_type {testcase_type}")
                return Response({
                    'error': 'Problem Testcase GET Fail',
                    'detail': 'Directory not found for the given testcase_type'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Function to read .in and .out files from a directory
            def read_files(sub_directory):
                data = {}
                try:
                    for in_file in sub_directory.glob('*.in'):
                        file_number = in_file.stem  # Get the file number (e.g., "1" from "1.in")
                        out_file = sub_directory / f"{file_number}.out"
                        if out_file.exists():
                            with open(in_file, 'r') as infile, open(out_file, 'r') as outfile:
                                data[file_number] = {
                                    "input": infile.read().strip(),
                                    "output": outfile.read().strip()
                                }
                        else:
                            raise FileNotFoundError(f"Output file corresponding to {in_file.name} not found in {sub_directory}")
                except Exception as e:
                    logger.error(f"Error reading files in directory {sub_directory}: {str(e)}", exc_info=True)
                    raise IOError(f"Error reading files in directory {sub_directory}: {str(e)}")
                return data, len(data)

            # Read the files and return the response
            contents, contents_num = read_files(directory_path)

            final_response_data = {
                'message': f'Testcase Retrieval Success : {contents_num} testcase(s) found',
                'testcase_name': title + testcase_type,
                'contents': contents
            }
            logger.info(f"Testcase retrieval successful for problem ID {problem_id}")
            return Response(final_response_data, status=status.HTTP_200_OK)

        except Problem.DoesNotExist:
            logger.warning(f"Problem with ID {problem_id} not found in GET request")
            return Response({
                'error': 'Problem Testcase GET Fail',
                'detail': f'Problem with ID {problem_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except FileNotFoundError as fnf_error:
            logger.warning(f"File not found error during GET request: {str(fnf_error)}")
            return Response({
                'error': 'Problem Testcase GET Fail',
                'detail': str(fnf_error)},
                status=status.HTTP_404_NOT_FOUND
            )
        except IOError as io_error:
            logger.error(f"I/O error occurred during GET request: {str(io_error)}", exc_info=True)
            return Response({
                'error': 'Problem Testcase GET Fail',
                'detail': str(io_error)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Unexpected error during GET request for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Testcase GET Fail',
                'detail': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # Update testcase (replace all files)
    def put(self, request, problem_id):
        logger.info(f"Problem testcase update initiated for problem ID: {problem_id}")

        testcase_type = request.GET.get('testcase_type')
        if not testcase_type or testcase_type not in {'_run', '_submit'}:
            logger.warning("testcase_type query parameter missing or invalid in PUT request")
            return Response({
                'error': 'Problem Testcase PUT Fail',
                'detail': 'testcase_type query parameter is required and must be either _run or _submit'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_serializer = ZipFileUploadSerializer(data=request.data)
        if file_serializer.is_valid():
            try:
                # Retrieve the problem title
                title = Problem.objects.values_list('title', flat=True).get(pk=problem_id)
                logger.debug(f"Problem with ID {problem_id} found, title: {title}")

                # Generate the directory name based on the testcase_type
                testcase_dir_name = title.strip().lower().replace(" ", "_") + testcase_type

                # Extract the zip file from the request
                zip_file = request.FILES.get('testcase_zip')
                if not zip_file:
                    logger.warning("testcase_zip file missing in PUT request")
                    return Response({
                        'error': 'Problem Testcase PUT Fail',
                        'detail': 'testcase_zip file is required'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Define the extraction path
                extract_path = Path(TESTCASE_BASE_DIR) / testcase_dir_name

                # Remove existing files in the directory before replacing
                if extract_path.exists():
                    for file in extract_path.glob("*"):
                        file.unlink()

                extract_path.mkdir(parents=True, exist_ok=True)

                # Define the full path to save the uploaded zip file
                zip_file_path = extract_path / zip_file.name

                # Save the uploaded zip file
                with open(zip_file_path, 'wb') as f:
                    for chunk in zip_file.chunks():
                        f.write(chunk)
                
                logger.debug(f"Zip file saved successfully at {zip_file_path}")

                # Extract the contents of the zip file
                extract_zip(zip_file_path, extract_path)
                logger.debug(f"Zip file extracted successfully at {extract_path}")

                # Collect file information from the extracted contents
                data = collect_file_info(extract_path)

                # Save the collected information to an info.json file
                info_json_path = extract_path / 'info.json'
                save_to_json(data, info_json_path)
                logger.debug(f"File information saved as JSON at {info_json_path}")

                # Remove the uploaded zip file after extraction
                zip_file_path.unlink()
                logger.info(f"Problem testcase update successful for problem ID {problem_id}")

                # Prepare the response data
                response_data = {
                    'message': 'Testcase File Update Success',
                    'testcase_name': testcase_dir_name,
                    'extracted_files': data.get('testcase_number', 0),
                }

                return Response(response_data, status=status.HTTP_200_OK)

            except Problem.DoesNotExist:
                logger.warning(f"Problem with ID {problem_id} not found in PUT request")
                return Response({
                    'error': 'Problem Testcase PUT Fail',
                    'detail': f'Problem with ID {problem_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            except zipfile.BadZipFile:
                logger.warning("Uploaded file is not a valid zip file")
                return Response({
                    'error': 'Problem Testcase PUT Fail',
                    'detail': 'Uploaded file is not a valid zip file'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except IOError as io_error:
                logger.error(f"File I/O error occurred during PUT request: {str(io_error)}", exc_info=True)
                return Response({
                    'error': 'Problem Testcase PUT Fail',
                    'detail': f'File I/O error occurred: {str(io_error)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            except Exception as e:
                logger.error(f"Unexpected error during PUT request for problem ID {problem_id}: {str(e)}", exc_info=True)
                return Response({
                    'error': 'Problem Testcase PUT Fail',
                    'detail': f'An unexpected error occurred: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            logger.warning("Invalid file type provided in PUT request, expected a zip file")
            return Response({
                'error': 'Problem Testcase PUT Fail',
                'detail': 'Invalid file type, expected a zip file'},
                status=status.HTTP_400_BAD_REQUEST
            )

    # Delete testcase (remove entire directory)
    def delete(self, request, problem_id):
        logger.info(f"Problem testcase deletion initiated for problem ID: {problem_id}")

        testcase_type = request.GET.get('testcase_type')
        if not testcase_type or testcase_type not in {'_run', '_submit'}:
            logger.warning("testcase_type query parameter missing or invalid in DELETE request")
            return Response({
                'error': 'Problem Testcase DELETE Fail',
                'detail': 'testcase_type query parameter is required and must be either _run or _submit'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Retrieve the problem title
            title = Problem.objects.values_list('title', flat=True).get(pk=problem_id)
            logger.debug(f"Problem with ID {problem_id} found, title: {title}")

            # Generate the directory name based on the testcase_type
            testcase_dir_name = title.strip().lower().replace(" ", "_") + testcase_type

            # Define the path to the directory to be deleted
            delete_path = Path(TESTCASE_BASE_DIR) / testcase_dir_name

            if delete_path.exists() and delete_path.is_dir():
                for file in delete_path.glob("*"):
                    file.unlink()  # Remove all files in the directory
                delete_path.rmdir()  # Remove the directory itself

                logger.info(f"Testcase directory deleted successfully for problem ID {problem_id} and testcase_type {testcase_type}")
                return Response({
                    'message': 'Testcase Directory Delete Success',
                    'testcase_name': testcase_dir_name},
                    status=status.HTTP_204_NO_CONTENT
                )
            else:
                logger.warning(f"Testcase directory not found for problem ID {problem_id} and testcase_type {testcase_type}")
                return Response({
                    'error': 'Problem Testcase DELETE Fail',
                    'detail': 'Testcase directory not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

        except Problem.DoesNotExist:
            logger.warning(f"Problem with ID {problem_id} not found in DELETE request")
            return Response({
                'error': 'Problem Testcase DELETE Fail',
                'detail': f'Problem with ID {problem_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Unexpected error during DELETE request for problem ID {problem_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Testcase DELETE Fail',
                'detail': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


"""
[사용자의 특정 문제 제출 내역 불러오기]
"""
# problem_submission_list
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_problem_submission_list(request, problem_id):
    try:
        logger.info(f"Problem submission list request initiated for problem ID: {problem_id}")

        # Check for Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning("Invalid Token or No access token provided in submission list request")
            return Response({
                "error": "Problem Submission List GET Fail",
                "detail": "Invalid Token or No access token provided"
            }, status=status.HTTP_401_UNAUTHORIZED)

        access_token = auth_header.split(' ')[1]
        social_token = SocialToken.objects.get(token=access_token)
        user_id = social_token.account_id
        logger.debug(f"User ID {user_id} retrieved from social token")

        # Validate that the problem exists
        if not Problem.objects.filter(id=problem_id).exists():
            logger.warning(f"Problem with ID {problem_id} does not exist")
            return Response({
                'error': 'Problem Submission List GET Fail',
                'detail': f'Problem with id {problem_id} does not exist'
            }, status=status.HTTP_404_NOT_FOUND)

        # Retrieve all submissions related to the given problem_id for the current user
        submissions = Submission.objects.filter(problem_id=problem_id, user_id=user_id).order_by('-submitted_at')
        # Serialize the submissions, excluding submission_detail
        serializer = SubmissionSerializer(submissions, many=True, context={'exclude_submission_detail': True})
        
        logger.info(f"Problem submission list retrieval successful for problem ID {problem_id}: {len(serializer.data)} submissions found")
        return Response({
            'message': f'Problem Submission List Retrieval Success: {len(serializer.data)} submissions found',
            'data': serializer.data},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Unexpected error during problem submission list retrieval for problem ID {problem_id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'Problem Submission List GET Fail',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

"""
[사용자의 특정 문제 제출 상세 정보 불러오기]
"""
# problem_submission_detail
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_problem_submission_detail(request, problem_id, submission_id):
    try:
        logger.info(f"Problem submission detail request initiated for problem ID: {problem_id}, submission ID: {submission_id}")

        # Check for Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning("Invalid Token or No access token provided in submission detail request")
            return Response({
                "error": "Problem Submission Detail GET Fail",
                "detail": "Invalid Token or No access token provided"
            }, status=status.HTTP_401_UNAUTHORIZED)

        access_token = auth_header.split(' ')[1]
        social_token = SocialToken.objects.get(token=access_token)
        user_id = social_token.account_id
        logger.debug(f"User ID {user_id} retrieved from social token")

        # Validate that the problem exists
        if not Problem.objects.filter(id=problem_id).exists():
            logger.warning(f"Problem with ID {problem_id} does not exist")
            return Response({
                'error': 'Problem Submission Detail GET Fail',
                'detail': f'Problem with id {problem_id} does not exist'
            }, status=status.HTTP_404_NOT_FOUND)

        # Retrieve the specific submission related to the given problem_id and submission_id for the current user
        try:
            submission = Submission.objects.select_related('submission_detail').get(id=submission_id, problem_id=problem_id, user_id=user_id)
            logger.debug(f"Submission ID {submission_id} found for problem ID {problem_id}")
        except Submission.DoesNotExist:
            logger.warning(f"Submission with ID {submission_id} for problem ID {problem_id} not found")
            return Response({
                'error': 'Problem Submission Detail GET Fail',
                'detail': 'Submission not found for this problem'
            }, status=status.HTTP_404_NOT_FOUND)

        # Serialize the submission including submission_detail
        serializer = SubmissionSerializer(submission)
        logger.info(f"Problem submission detail retrieval successful for submission ID {submission_id}")
        return Response({
            'message': 'Problem Submission Detail Retrieval Success',
            'data': serializer.data},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Unexpected error during problem submission detail retrieval for submission ID {submission_id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'Problem Submission Detail GET Fail',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#################################################
#                 Code Judgement                #
#################################################

def do_judge(language, main_code, user_code, testcase_dir_name, max_cpu_time, max_real_time, max_memory):
    logger.info(f"Judgement process initiated for language: {language}, testcase_dir_name: {testcase_dir_name}")

    language_config = lang_config[language]

    with SubmissionDriver(RUN_BASE_DIR, testcase_dir_name) as dirs:
        """
        Prepare paths for Code Judgement
        """
        submission_dir, testcase_dir = dirs
        if "compile" in language_config:
            main_src_path = os.path.join(submission_dir, language_config["compile"]["src_name"])  # Main file path
            user_src_path = os.path.join(submission_dir, language_config["compile"]["solution_name"])  # User solution file path
        else:  # js
            main_src_path = os.path.join(submission_dir, language_config["run"]["exe_name"])  # Main file path
            user_src_path = os.path.join(submission_dir, language_config["run"]["solution_name"])  # User solution file path

        logger.debug(f"Main source path: {main_src_path}, User source path: {user_src_path}")

        """
        Prepare User Code and Main Execution Code 
        """
        try:
            with open(main_src_path, "w", encoding="utf-8") as f:
                f.write(main_code)  # Main code
            with open(user_src_path, "w", encoding="utf-8") as f:
                f.write(user_code)  # User code
                if language == "js":
                    f.write(r"""module.exports = { solution };""")
            logger.debug(f"User code and main code written to respective paths")
        except IOError as io_error:
            logger.error(f"Failed to write code files: {str(io_error)}", exc_info=True)
            raise

        """
        Compile  
        """
        compile_error_msg = ""
        try:
            if "compile" in language_config:
                exe_path, compile_error_msg = Compiler().compile(
                    compile_config=language_config["compile"], src_path=main_src_path, output_dir=submission_dir
                )
            else:  # js
                exe_path = main_src_path

            logger.info(f"Compilation process completed. Executable path: {exe_path}")
        except Exception as e:
            logger.error(f"Compilation failed: {str(e)}", exc_info=True)
            raise

        """
        Compile Error + Undefined Behavior (No compile error message even when compile error occurred)
        """
        if compile_error_msg or (language != "java" and not os.path.exists(exe_path)):
            logger.warning(f"Compilation error or executable not found for language: {language}, error: {compile_error_msg}")
            return None, compile_error_msg

        """
        Code Judgement Executing Instance
        """
        judge_client = Judger(
            run_config=language_config["run"],
            exe_path=exe_path,
            max_cpu_time=max_cpu_time,
            max_real_time=max_real_time,
            max_memory=max_memory,
            testcase_dir=testcase_dir,
            submission_dir=submission_dir
        )
        logger.info(f"Judgement client initialized for execution.")

        """
        Real Execution (REAL RUN)
        """
        results = judge_client.run()
        logger.info(f"Judgement execution completed with results.")
    
    return results, compile_error_msg


"""
[예제 테스트 케이스 돌리기 - Run]
"""
# problem-run
@api_view(['POST'])
def problem_run(request, problem_id):
    """ Preprocessing for Code Judgement Execution """
    try:
        logger.info(f"Problem run request initiated for problem ID: {problem_id}")

        # Validate the incoming request data
        serializer = ProblemRunRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Validation failed for problem run request: {serializer.errors}")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract validated data
        testcase = serializer.validated_data.get('testcase')
        user_code = serializer.validated_data.get('solution')
        logger.debug(f"Testcase and solution code extracted from the request data.")

        # Obtain selected language from query parameters
        language_id = request.query_params.get('language_id')
        if not language_id:
            logger.warning(f"language_id query parameter missing in problem run request")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'language_id is required as a query parameter'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            language = Language.objects.get(id=language_id)
            language_type = language.language
            logger.debug(f"Language ID {language_id} found, language: {language_type}")
        except Language.DoesNotExist:
            logger.warning(f"Language with ID {language_id} not found")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'Language type not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Obtain testcase name using title
        try:
            title = Problem.objects.values_list('title', flat=True).get(pk=problem_id)
            logger.debug(f"Problem with ID {problem_id} found")
        except Problem.DoesNotExist:
            logger.warning(f"Problem with ID {problem_id} not found")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'Requested problem does not exist in DB'},
                status=status.HTTP_404_NOT_FOUND
            )
        try:
            max_constraint = CodeJudgeMaxConstraint.objects.get(problem_id=problem_id, language_id=language_id)
        except CodeJudgeMaxConstraint.DoesNotExist:
            logger.warning(f"Maximum Constraints for problem ID {problem_id} or language ID {language_id} not found")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'Maximum Constraints for requested problem and language does not exist in DB'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        testcase_dir_name = title.strip().lower().replace(" ", "_") + "_run"

        # Retrieve the main code for the problem and language
        try:
            main_code = InitCode.objects.values_list('run_code', flat=True).get(problem_id=problem_id, language_id=language_id)
            logger.debug(f"Main code retrieved for problem ID {problem_id} and language ID {language_id}")
        except InitCode.DoesNotExist:
            logger.warning(f"Main code for problem ID {problem_id} and language ID {language_id} not found")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': '`Main` code for the problem and language is not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        """
        Code Judgement Execution
        """
        logger.info(f"Starting code judgement execution for problem ID {problem_id}")
        judge_result, compile_error_msg = do_judge(
            language_type,
            main_code,
            user_code,
            testcase_dir_name,
            max_constraint.max_cpu_time,
            max_constraint.max_real_time,
            max_constraint.max_memory
        )

        if not judge_result:  # Something wrong..
            if compile_error_msg:
                logger.warning(f"Compile error during judgement execution: {compile_error_msg}")
                return Response({
                    'message': 'COMPILE_ERROR',
                    'err_msg': compile_error_msg
                }, status=status.HTTP_200_OK
                )
            logger.error("COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        """
            # [Compile Error Handling - Error Message]
            # - js, python : result['output']
            # - c, cpp, java : compile_error_msg
        """
        """ Compose response data with the code judgement execution result """
        response_data = {}
        for result in judge_result:
            # SOLVED == -2 / WRONG == -1
            result['result'] = -2 if result['result'] == 0 else result['result']
            testcase_result = SUBMISSION_RESULT.get(result['result'], "")
            testcase_num = result['testcase']
            if not testcase_result:
                logger.error(f"Unexpected run result for testcase number {testcase_num}: {testcase_result}")
                return Response({
                    'error': 'Problem Run POST Fail',
                    'detail': f'Unexpected Run result - {testcase_num} testcase result : {testcase_result}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            result_info = {
                'run_result': testcase_result,
                'is_solved': False,
                'testcase': testcase[testcase_num],
                'run_time': result['cpu_time'],
                'memory': result['memory'],
                'user_out': "",
                'stdout': result['stdout'],
                'err_msg': ""
            }
            
            if result['result'] == 4:  # Runtime Error
                result_info['err_msg'] = result['output']
            elif -2 <= result['result'] <= -1:  # Successful Run
                result_info['is_solved'] = result['is_solved']
                result_info['user_out'] = result['output']
            response_data[testcase_num] = result_info
        
        logger.info(f"Problem run successful for problem ID {problem_id}")
        return Response({
            'message': 'Problem Run Successful Complete',
            'data': response_data},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Unexpected error during problem run for problem ID {problem_id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'Problem Run POST Fail',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

"""
[예제 테스트 케이스 돌리기 - Run (Using Celery)]
"""
@api_view(['POST'])
def problem_run_for_task(request, problem_id):
    """ Preprocessing for Code Judgement Execution """
    try:
        logger.info(f"Problem run request initiated for problem ID: {problem_id}")

        # Validate the incoming request data
        serializer = ProblemRunRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Validation failed for problem run request: {serializer.errors}")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Extract validated data
        testcase = serializer.validated_data.get('testcase')
        user_code = serializer.validated_data.get('solution')
        logger.debug(f"Testcase and solution code extracted from the request data.")

        # Obtain selected language from query parameters
        language_id = request.query_params.get('language_id')
        if not language_id:
            logger.warning(f"language_id query parameter missing in problem run request")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'language_id is required as a query parameter'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            language = Language.objects.get(id=language_id)
            language_type = language.language
            logger.debug(f"Language ID {language_id} found, language: {language_type}")
        except Language.DoesNotExist:
            logger.warning(f"Language with ID {language_id} not found")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'Language type not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Obtain testcase name using title
        try:
            title = Problem.objects.values_list('title', flat=True).get(pk=problem_id)
            logger.debug(f"Problem with ID {problem_id} found")
        except Problem.DoesNotExist:
            logger.warning(f"Problem with ID {problem_id} not found")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'Requested problem does not exist in DB'
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            max_constraint = CodeJudgeMaxConstraint.objects.get(problem_id=problem_id, language_id=language_id)
        except CodeJudgeMaxConstraint.DoesNotExist:
            logger.warning(f"Maximum Constraints for problem ID {problem_id} or language ID {language_id} not found")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'Maximum Constraints for requested problem and language does not exist in DB'
            }, status=status.HTTP_404_NOT_FOUND)

        testcase_dir_name = title.strip().lower().replace(" ", "_") + "_run"

        # Retrieve the main code for the problem and language
        try:
            main_code = InitCode.objects.values_list('run_code', flat=True).get(problem_id=problem_id, language_id=language_id)
            logger.debug(f"Main code retrieved for problem ID {problem_id} and language ID {language_id}")
        except InitCode.DoesNotExist:
            logger.warning(f"Main code for problem ID {problem_id} and language ID {language_id} not found")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': '`Main` code for the problem and language is not found'
            }, status=status.HTTP_404_NOT_FOUND)

        """
        Code Judgement Execution
        """
        logger.info(f"Starting code judgement execution for problem ID {problem_id}")

        # Call do_judge function asynchronously
        try:
            judge_task = do_judge_for_task.delay(
                language_type,
                main_code,
                user_code,
                testcase_dir_name,
                max_constraint.max_cpu_time,
                max_constraint.max_real_time,
                max_constraint.max_memory
            )
        except Exception as e:
            logger.error(f"Failed to start do_judge_for_task: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': f'Failed to initiate the judgment task: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Check if the task completed successfully before calling .get()
        if not judge_task.ready():
            return Response({
                'message': 'Run Judgment task in progress',
                'submit_type': 'run',
                'task_id': judge_task.id,
                'status': 'PENDING'
            }, status=status.HTTP_202_ACCEPTED)

        # Fetch the result of the do_judge task (this may block if not ready)
        try:
            judge_result, compile_error_msg = judge_task.get(timeout=10)  # Timeout for getting the result
        except Exception as e:
            logger.error(f"Failed to get judgment task result: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': f'Failed to get judgment task result : {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # If there was a compile error
        if not judge_result:  # Something wrong..
            if compile_error_msg:
                logger.warning(f"Compile error during judgement execution: {compile_error_msg}")
                return Response({
                    'run_result': 'COMPILE_ERROR',
                    'err_msg': compile_error_msg
                }, status=status.HTTP_200_OK)
            logger.error("COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence")
            return Response({
                'error': 'Problem Run POST Fail',
                'detail': 'COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        """
            # [Compile Error Handling - Error Message]
            # - js, python : result['output']
            # - c, cpp, java : compile_error_msg
        """
        # Compose response data with the code judgement execution result
        response_data = {}
        for result in judge_result:
            # SOLVED == -2 / WRONG == -1
            result['result'] = -2 if result['result'] == 0 else result['result']
            testcase_result = SUBMISSION_RESULT.get(result['result'], "")
            testcase_num = result['testcase']
            if not testcase_result:
                logger.error(f"Unexpected run result for testcase number {testcase_num}: {testcase_result}")
                return Response({
                    'error': 'Problem Run POST Fail',
                    'detail': f'Unexpected Run result - {testcase_num} testcase result : {testcase_result}'
                }, status=status.HTTP_400_BAD_REQUEST)

            result_info = {
                'run_result': testcase_result,
                'is_solved': False,
                'testcase': testcase[testcase_num],
                'run_time': result['cpu_time'],
                'memory': result['memory'],
                'user_out': "",
                'stdout': result['stdout'],
                'err_msg': ""
            }

            if result['result'] == 4:  # Runtime Error
                result_info['err_msg'] = result['output']
            elif -2 <= result['result'] <= -1:  # Successful Run
                result_info['is_solved'] = result['is_solved']
                result_info['user_out'] = result['output']
            response_data[testcase_num] = result_info

        logger.info(f"Problem run successful for problem ID {problem_id}")
        return Response({
            'message': 'Problem Code Run Successful Complete',
            'data': response_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Unexpected error during problem run for problem ID {problem_id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'Problem Run POST Fail',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#################################################
#         Create Submission & Response          #
#################################################

def create_submission_and_response(**kwargs):
    try:
        logger.info(f"Creating submission record for user: {kwargs.get('user')} and problem: {kwargs.get('problem')}")

        # Parameters
        judge_result = kwargs.get('judge_result')
        compile_error_msg = kwargs.get('compile_error_msg')
        user = kwargs.get('user')
        problem = kwargs.get('problem')
        language = kwargs.get('language')
        user_code = kwargs.get('user_code')
        
        """
        Create Submission Record
        """
        submission = Submission.objects.create(
            user_id=user,
            problem_id=problem,
            language_id=language,
            submitted_code=user_code
        )
        submission_id = submission.id
        logger.debug(f"Submission record created with ID: {submission_id}")
        
        testcase_ids = []
        submission_results = []
        run_times = []
        memories = []
        submission_detail_response = []     # Response Data
        passed_num = 0                      # Solved Problem Number
        total_num = len(judge_result)      # Total Problem Number
        final_result = -2                   # Final Result of the submission
        problem_is_solved = True
        avg_run_time = 0
        avg_memory = 0

        """
        Organize Submission & SubmissionDetail
        """
        for result in judge_result:
            # SOLVED == -2 / WRONG == -1
            result['result'] = -2 if result['result'] == 0 else result['result']
            testcase_result = SUBMISSION_RESULT.get(result['result'], "")
            testcase_id = result['testcase']
            if not testcase_result:
                logger.error(f"[Organize Submission] Unexpected Submission result - {testcase_id} testcase result : {testcase_result}")
                raise ValueError(f'[Organize Submission] Unexpected Submission result - {testcase_id} testcase result : {testcase_result}')

            submission_detail = {
                'testcase_id': testcase_id,
                'result_info': {
                    'run_result': testcase_result,
                    'is_solved': False,
                    'run_time': result['cpu_time'],
                    'memory': result['memory'],
                    'user_out': "",
                }
            }

            avg_run_time += result['cpu_time']
            avg_memory += result['memory']

            if -2 <= result['result'] <= -1: # Successful Run
                problem_is_solved = (problem_is_solved and result['is_solved'])
                submission_detail['result_info']['is_solved'] = result['is_solved']
                submission_detail['result_info']['user_out'] = result['output']
                if result['is_solved']:
                    passed_num += 1
            if final_result < result['result']:
                final_result = result['result']

            # DB -> Append values to the lists
            testcase_ids.append(testcase_id)
            submission_results.append(testcase_result)
            run_times.append(str(result['cpu_time']))
            memories.append(str(result['memory']))

            submission_detail_response.append(submission_detail)

        """
        Post-processing
        """
        if len(judge_result):
            avg_run_time //= len(judge_result)
            avg_memory //= len(judge_result)
        else:
            avg_run_time = 0
            avg_memory = 0

        testcase_ids = ','.join(testcase_ids)
        submission_results = ','.join(submission_results)
        run_times = ','.join(run_times)
        memories = ','.join(memories)

        """
        Create SubmissionDetail Record
        """
        SubmissionDetail.objects.create(
            submission_id=submission,
            testcase_id=testcase_ids,
            submission_result=submission_results,
            run_time=run_times,
            memory=memories
        )
        logger.debug(f"SubmissionDetail record created for submission ID: {submission_id}")

        """
        Update Submission Record
        """
        submission.passed_num = passed_num
        submission.total_num = total_num
        submission_result = SUBMISSION_RESULT.get(final_result, "")
        submission.avg_run_time = avg_run_time
        submission.avg_memory = avg_memory

        if submission_result:
            submission.final_result = submission_result
        else:
            logger.error(f"[Update Submission Record] Unexpected Submission result -> {final_result}")
            raise ValueError(f'[Update Submission Record] Unexpected Submission result -> {final_result}')
        
        submission.save()
        logger.info(f"Submission record updated with final results for submission ID: {submission_id}")
        
        submissions_a = Submission.objects.filter(problem_id=problem, user_id=user).order_by('-submitted_at')
        serializer = SubmissionSerializer(submissions_a, many=True, context={'exclude_submission_detail': True})
        
        if len(serializer.data) <= 1:
            problem.attempt_number = F('attempt_number') + 1
        
        # Problem Solved
        if final_result == -2:
            solved_num = 0
            for i in serializer.data:
                if i['final_result'] == "SOLVED":
                    solved_num += 1
            if solved_num == 1:
                problem.solve_number = F('solve_number') + 1

        problem.save()
        logger.info(f"Problem record updated for problem ID: {problem.id}")

        """
        Compose response data with the code judgement execution result
        """
        response_data = {
            'submission_id': submission_id,
            'final_result': submission_result,
            'solution': user_code,
            'passed_num': passed_num,
            'total_num': total_num,
            'avg_run_time': avg_run_time,
            'avg_memory': avg_memory,
            'submission_detail': submission_detail_response,
            'submitted_at': submission.submitted_at,
        }

        logger.info(f"Submission response data composed successfully for submission ID: {submission_id}")
        return response_data

    except Exception as e:
        logger.error(f"Submission creation failed: {str(e)}", exc_info=True)
        raise ValueError(f"Submission creation failed: {str(e)}")


"""
[문제 풀이 코드 제출하기 - Submit]
"""

# problem-submit
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ratelimit(key='user', rate='5/m', method='POST', block=True)
def problem_submit(request, problem_id):
    """
    Preprocessing for Code Judgement Execution
    """
    try:
        logger.info(f"Problem submit request initiated for problem ID: {problem_id}")

        # Check for Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning(f"Invalid access token or No access token provided in problem submit request")
            return Response({
                "error": "Problem Submit POST Fail",
                "detail": "Invalid access token or No access token provided"
            }, status=status.HTTP_401_UNAUTHORIZED)

        access_token = auth_header.split(' ')[1]
        social_token = SocialToken.objects.get(token=access_token)
        user_id = social_token.account_id

        # Verify that the user exists
        user = get_object_or_404(User, pk=user_id)
        logger.debug(f"User ID {user_id} verified")

        # Validate the incoming request data
        serializer = ProblemSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Validation failed for problem submit request: {serializer.errors}")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract validated data
        user_code = serializer.validated_data.get('solution')
        logger.debug(f"User solution code extracted")

        # Obtain selected language from query parameters
        language_id = request.query_params.get('language_id')
        if not language_id:
            logger.warning(f"Query parameter 'language_id' missing in problem submit request")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'Query parameter "language_id" is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        language_type = None

        # Generate cache key for this submission based on user_id, problem_id, and hashed user_code
        cache_key = generate_submission_cache_key(user_id, problem_id, language_id, user_code)
        
        # Check if the result is already cached
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Returning cached result for user ID: {user_id}, problem ID: {problem_id}, language ID: {language_id}")
            return Response({
                'message': 'Problem Code Submit Successful Complete - Duplicate Submission',
                'data': cached_data  # Cached submission result
            }, status=status.HTTP_200_OK)
        
        try:
            language = Language.objects.get(id=language_id)
            language_type = language.language
            logger.debug(f"Language ID {language_id} found, language: {language_type}")
        except Language.DoesNotExist:
            logger.warning(f"Language with ID {language_id} not found")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'Language type not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Obtain the problem title to create the testcase directory name
        try:
            problem = Problem.objects.get(pk=problem_id)
            logger.debug(f"Problem with ID {problem_id} found")
        except Problem.DoesNotExist:
            logger.warning(f"Problem with ID {problem_id} not found")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'Requested problem does not exist in DB'},
                status=status.HTTP_404_NOT_FOUND
            )
            
        try:
            max_constraint = CodeJudgeMaxConstraint.objects.get(problem_id=problem_id, language_id=language_id)
            logger.debug(f"Max Constraint with Problem ID {problem_id} and Language ID {language_id} found")
        except CodeJudgeMaxConstraint.DoesNotExist:
            logger.warning(f"Maximum Constraints for problem ID {problem_id} or language ID {language_id} not found")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'Maximum Constraints for requested problem and language does not exist in DB'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        testcase_dir_name = problem.title.strip().lower().replace(" ", "_") + "_submit"

        # Retrieve the main code for the problem and language
        try:
            main_code = InitCode.objects.values_list('run_code', flat=True).get(problem_id=problem_id, language_id=language_id)
            logger.debug(f"Main code retrieved for problem ID {problem_id} and language ID {language_id}")
        except InitCode.DoesNotExist:
            logger.warning(f"Main code for problem ID {problem_id} and language ID {language_id} not found")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': '`Main` code for the problem and language is not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        """
        Code Judgement Execution
        """
        logger.info(f"Starting code judgement execution for problem ID {problem_id}")
        judge_result, compile_error_msg = do_judge(
            language_type,
            main_code,
            user_code,
            testcase_dir_name,
            max_constraint.max_cpu_time,
            max_constraint.max_real_time,
            max_constraint.max_memory
        )
        
        if not judge_result:  # Something wrong..
            if compile_error_msg:
                logger.warning(f"Compile error during judgement execution: {compile_error_msg}")
                return Response({
                    'run_result': 'COMPILE_ERROR',
                    'err_msg': compile_error_msg
                }, status=status.HTTP_200_OK
                )
            logger.error("COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        """
        Submission-related database operation & Response composition
        """
        try:
            response_data = create_submission_and_response(
                judge_result=judge_result, 
                compile_error_msg=compile_error_msg, 
                user=user, 
                problem=problem, 
                language=language, 
                user_code=user_code
            )
            logger.info(f"Submission and response creation successful for problem ID {problem_id}")
        except ValueError as e:
            logger.warning(f"Submission creation failed: {str(e)}")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Cache the result for future identical submissions
        cache.set(cache_key, response_data, timeout=86400)  # Cache for 24 hours or adjust as needed

        return Response({
            'message': 'Problem Code Submit Successful Complete',
            'data': response_data},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Unexpected error during problem submit for problem ID {problem_id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'Problem Submit POST Fail',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)   


"""
[문제 풀이 코드 제출하기 - Submit (Using Celery)]
"""

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ratelimit(key='user', rate='5/m', method='POST', block=True)
def problem_submit_for_task(request, problem_id):
    """
    Preprocessing for Code Judgement Execution
    """
    try:
        logger.info(f"Problem submit request initiated for problem ID: {problem_id}")

        # Check for Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning(f"Invalid access token or No access token provided in problem submit request")
            return Response({
                "error": "Problem Submit POST Fail",
                "detail": "Invalid access token or No access token provided"
            }, status=status.HTTP_401_UNAUTHORIZED)

        access_token = auth_header.split(' ')[1]
        social_token = SocialToken.objects.get(token=access_token)
        user_id = social_token.account_id

        # Verify that the user exists
        user = get_object_or_404(User, pk=user_id)
        logger.debug(f"User ID {user_id} verified")

        # Validate the incoming request data
        serializer = ProblemSubmitSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Validation failed for problem submit request: {serializer.errors}")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Extract validated data
        user_code = serializer.validated_data.get('solution')
        logger.debug(f"User solution code extracted")

        # Obtain selected language from query parameters
        language_id = request.query_params.get('language_id')
        if not language_id:
            logger.warning(f"Query parameter 'language_id' missing in problem submit request")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'Query parameter "language_id" is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            language = Language.objects.get(id=language_id)
            language_type = language.language
            logger.debug(f"Language ID {language_id} found, language: {language_type}")
        except Language.DoesNotExist:
            logger.warning(f"Language with ID {language_id} not found")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'Language type not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Obtain the problem title to create the testcase directory name
        try:
            problem = Problem.objects.get(pk=problem_id)
            logger.debug(f"Problem with ID {problem_id} found")
        except Problem.DoesNotExist:
            logger.warning(f"Problem with ID {problem_id} not found")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'Requested problem does not exist in DB'
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            max_constraint = CodeJudgeMaxConstraint.objects.get(problem_id=problem_id, language_id=language_id)
            logger.debug(f"Max Constraint with Problem ID {problem_id} and Language ID {language_id} found")
        except CodeJudgeMaxConstraint.DoesNotExist:
            logger.warning(f"Maximum Constraints for problem ID {problem_id} or language ID {language_id} not found")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'Maximum Constraints for requested problem and language does not exist in DB'
            }, status=status.HTTP_404_NOT_FOUND)

        testcase_dir_name = problem.title.strip().lower().replace(" ", "_") + "_submit"

        # Retrieve the main code for the problem and language
        try:
            main_code = InitCode.objects.values_list('run_code', flat=True).get(problem_id=problem_id, language_id=language_id)
            logger.debug(f"Main code retrieved for problem ID {problem_id} and language ID {language_id}")
        except InitCode.DoesNotExist:
            logger.warning(f"Main code for problem ID {problem_id} and language ID {language_id} not found")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': '`Main` code for the problem and language is not found'
            }, status=status.HTTP_404_NOT_FOUND)

        """
        Code Judgement Execution
        """
        # Call do_judge function asynchronously
        try:
            logger.info(f"Starting code judgement execution for problem ID {problem_id}")
            judge_task = do_judge_for_task.delay(
                language_type,
                main_code,
                user_code,
                testcase_dir_name,
                max_constraint.max_cpu_time,
                max_constraint.max_real_time,
                max_constraint.max_memory
            )
        except Exception as e:
            logger.error(f"Failed to start do_judge_for_task: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': f'Failed to initiate the judgment task: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Check if the task completed successfully before calling .get()
        if not judge_task.ready():
            logger.debug(f"Submit Judgment task for problem ID {problem_id} is still in progress")
            return Response({
                'message': 'Submit Judgment task in progress',
                'submit_type': 'submit',
                'task_id': judge_task.id,
                'data': {
                    'user_id': user.id,
                    'problem_id': problem.id,
                    'language_id': language_id,
                    'user_code': user_code
                },
                'status': 'PENDING'
            }, status=status.HTTP_202_ACCEPTED)

        # Fetch the result of the do_judge task (this may block if not ready)
        try:
            judge_result, compile_error_msg = judge_task.get(timeout=10)  # Timeout for getting the result
        except Exception as e:
            logger.error(f"Failed to get judgment task result: {str(e)}", exc_info=True)
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': f'Failed to get judgment task result : {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # If there was a compile error
        if not judge_result:
            if compile_error_msg:
                logger.warning(f"Compile error during judgement execution: {compile_error_msg}")
                return Response({
                    'run_result': 'COMPILE_ERROR',
                    'err_msg': compile_error_msg
                }, status=status.HTTP_200_OK)
            logger.error("COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': 'COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            response_data = create_submission_and_response(
                judge_result=judge_result, 
                compile_error_msg=compile_error_msg, 
                user=user, 
                problem=problem, 
                language=language, 
                user_code=user_code
            )
            logger.info(f"Submission and response creation successful for problem ID {problem_id}")
        except ValueError as e:
            logger.warning(f"Submission creation failed: {str(e)}")
            return Response({
                'error': 'Problem Submit POST Fail',
                'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        logger.info(f"Code Submit Successful for problem ID {problem_id}")
        return Response({
            'message': 'Problem Code Submit Successful Complete',
            'data': submission_response_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Unexpected error during problem submit for problem ID {problem_id}: {str(e)}", exc_info=True)
        return Response({
            'error': 'Problem Submit POST Fail',
            'detail': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def code_judge_task_status(request, task_id):
    # Extract data from the request (make sure you have `task_id` and `submit_type`)
    submit_type = request.query_params.get('submit_type')  # Default to 'submit' if not provided

    try:
        # Validate that the task_id and submit_type are provided
        if not task_id:
            logger.warning("Task ID is missing in code_judge_task_status request")
            return Response({
                'error': 'Judge Task Status POST Fail',
                'detail': 'Task ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not submit_type:
            logger.warning("Submit type is missing in code_judge_task_status request")
            return Response({
                'error': 'Judge Task Status POST Fail',
                'detail': 'Submit type is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        logger.info(f"Fetching task status for task ID: {task_id}, submit_type: {submit_type}")

        # Fetch the task result using the Celery task ID
        task_result = AsyncResult(task_id)

        # Check if the task is still pending
        if task_result.state == 'PENDING':
            logger.debug(f"Task ID {task_id} is still pending")
            return Response({
                'message': f'Problem {submit_type.capitalize()} task in progress or Invalid task id',
                'task_id': task_id,
                'status': 'PENDING'
            }, status=status.HTTP_202_ACCEPTED)

        # Check if the task failed
        elif task_result.state == 'FAILURE':
            logger.error(f"Task ID {task_id} failed with error: {str(task_result.info)}")
            return Response({
                'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                'task_id': task_id,
                'status': 'FAILURE',
                'detail': str(task_result.info)  # Task failure reason
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # If the task is successful, return the result
        elif task_result.state == 'SUCCESS':
            try:
                judge_result, compile_error_msg = task_result.result
                logger.debug(f"Task ID {task_id} completed successfully")
            except ValueError as e:
                logger.error(f"Error retrieving task result for task ID {task_id}: {str(e)}")
                return Response({
                    'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                    'detail': f"Error retrieving task result: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Handle the response based on the submit_type
            if submit_type == 'run':
                logger.info(f"Handling 'run' type for task ID {task_id}")
                # If there was a compile error
                if not judge_result:  # Something went wrong
                    if compile_error_msg:
                        logger.warning(f"Compile error during judgment execution for task ID {task_id}: {compile_error_msg}")
                        return Response({
                            'run_result': 'COMPILE_ERROR',
                            'err_msg': compile_error_msg
                        }, status=status.HTTP_200_OK)

                    logger.error(f"COMPILE_ERROR with no message for task ID {task_id}")
                    return Response({
                        'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                        'detail': 'COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                """
                    # [Compile Error Handling - Error Message]
                    # - js, python : result['output']
                    # - c, cpp, java : compile_error_msg
                """
                # Compose response data with the code judgment execution result
                response_data = {}

                for result in judge_result:
                    # SOLVED == -2 / WRONG == -1
                    result['result'] = -2 if result['result'] == 0 else result['result']
                    testcase_result = SUBMISSION_RESULT.get(result['result'], "")
                    testcase_num = result['testcase']
                    if not testcase_result:
                        logger.error(f"Unexpected run result for testcase number {testcase_num}: {testcase_result}")
                        return Response({
                            'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                            'detail': f'Unexpected Run result - {testcase_num} testcase result : {testcase_result}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    result_info = {
                        'run_result': testcase_result,
                        'is_solved': False,
                        'testcase': testcase[testcase_num],
                        'run_time': result['cpu_time'],
                        'memory': result['memory'],
                        'user_out': "",
                        'stdout': result['stdout'],
                        'err_msg': ""
                    }

                    if result['result'] == 4:  # Runtime Error
                        result_info['err_msg'] = result['output']
                    elif -2 <= result['result'] <= -1:  # Successful Run
                        result_info['is_solved'] = result['is_solved']
                        result_info['user_out'] = result['output']
                    response_data[testcase_num] = result_info

                logger.info(f"Problem run successful for task ID {task_id}")
                return Response({
                    'message': 'Problem Code Run Successful Complete',
                    'data': response_data
                }, status=status.HTTP_200_OK)

            elif submit_type == 'submit':
                logger.info(f"Handling 'submit' type for task ID {task_id}")
                data = request.data.get('data', None)

                if not judge_result:  # Something wrong
                    if compile_error_msg:
                        logger.warning(f"Compile error during judgement execution for task ID {task_id}: {compile_error_msg}")
                        return Response({
                            'run_result': 'COMPILE_ERROR',
                            'err_msg': compile_error_msg
                        }, status=status.HTTP_200_OK)

                    logger.error(f"COMPILE_ERROR - Undefined Behavior: No message for task ID {task_id}")
                    return Response({
                        'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                        'detail': 'COMPILE_ERROR - Undefined Behavior: No compiler error message despite the error occurrence'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                if data is None:
                    logger.error(f"Data required for submission response is missing for task ID {task_id}")
                    return Response({
                        'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                        'detail': 'Data required for submission response does not exist'
                    }, status=status.HTTP_400_BAD_REQUEST)

                try:
                    user_id = data.get('user_id', None)
                    problem_id = data.get('problem_id', None)
                    language_id = data.get('language_id', None)
                    user_code = data.get('user_code', None)

                    user = User.objects.get(id=user_id)
                    problem = Problem.objects.get(id=problem_id)
                    language = Language.objects.get(id=language_id)

                    response_data = create_submission_and_response(
                        judge_result=judge_result,
                        compile_error_msg=compile_error_msg,
                        user=user,
                        problem=problem,
                        language=language,
                        user_code=user_code
                    )
                    logger.info(f"Submission and response creation successful for problem ID {problem_id}")

                    return Response({
                        'message': 'Problem Code Submit Successful Complete',
                        'data': response_data  # Your custom result
                    }, status=status.HTTP_200_OK)

                except User.DoesNotExist:
                    logger.error(f"User with ID {user_id} not found")
                    return Response({
                        'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                        'detail': f"User with ID {user_id} not found"
                    }, status=status.HTTP_404_NOT_FOUND)

                except Problem.DoesNotExist:
                    logger.error(f"Problem with ID {problem_id} not found")
                    return Response({
                        'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                        'detail': f"Problem with ID {problem_id} not found"
                    }, status=status.HTTP_404_NOT_FOUND)

                except Language.DoesNotExist:
                    logger.error(f"Language with ID {language_id} not found")
                    return Response({
                        'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                        'detail': f"Language with ID {language_id} not found"
                    }, status=status.HTTP_404_NOT_FOUND)

                except Exception as e:
                    logger.error(f"Unexpected error for task ID {task_id}: {str(e)}", exc_info=True)
                    return Response({
                        'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
                        'detail': str(e)
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Handle any other exceptions
    except Exception as e:
        logger.error(f"Unexpected error during task status handling for task ID {task_id}: {str(e)}", exc_info=True)
        return Response({
            'error': f'Judge Task Status POST Fail - {submit_type.capitalize()}',
            'detail': f'{submit_type.capitalize()} Task Status Handling Error : {str(e)}',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'message': f'{submit_type.capitalize()} task is in state {task_result.state}',
        'task_id': task_id,
        'status': task_result.state
    }, status=status.HTTP_200_OK)