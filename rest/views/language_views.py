from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ..models import Language
from ..serializers import *
from django.db import IntegrityError
import logging

logger = logging.getLogger('rest')

class LanguageView(APIView):
    # Helper method to get the Language object
    def get_object(self, language_id):
        try:
            return Language.objects.get(id=language_id)
        except Language.DoesNotExist:
            logger.warning(f'Language with ID {language_id} does not exist.')
            return None
        except Exception as e:
            logger.error(f'Error fetching language with ID {language_id}: {str(e)}')
            raise e

    def get(self, request, language_id=None):
        try:
            if language_id:
                # Retrieve a specific language
                language = self.get_object(language_id)
                if language is None:
                    logger.info(f'GET request failed: Language with ID {language_id} not found.')
                    return Response({
                        'error': 'Language Detail GET Fail',
                        'detail': 'Language not found'
                    }, status=status.HTTP_404_NOT_FOUND)

                language_serializer = LanguageSerializer(language)
                logger.info(f'Language with ID {language_id} retrieved successfully.')
                return Response({
                    'message': 'Language Retrieval Success',
                    'data': language_serializer.data},
                    status=status.HTTP_200_OK
                )
            else:
                # Retrieve all languages
                languages = Language.objects.all().order_by('language')
                language_serializer = LanguageSerializer(languages, many=True)
                logger.info(f'All languages retrieved successfully. Count: {len(languages)}')
                return Response({
                    'message': 'Language List Retrieval Success',
                    'data': language_serializer.data},
                    status=status.HTTP_200_OK
                )
        
        except Exception as e:
            logger.error(f'GET request failed: {str(e)}')
            return Response({
                'error': 'Language GET Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            language_serializer = LanguageSerializer(data=request.data)
            if language_serializer.is_valid():
                language_serializer.save()
                logger.info(f'New language added successfully: {language_serializer.data}')
                return Response({
                    'message': 'New Language Addition Success',
                    'data': language_serializer.data},
                    status=status.HTTP_201_CREATED
                )
            logger.warning(f'POST request failed: Invalid data provided: {language_serializer.errors}')
            return Response({
                'error': 'Language POST Fail',
                'detail': language_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except IntegrityError as e:
            logger.warning('POST request failed: Language already exists.')
            return Response({
                'error': 'Language POST Fail',
                'detail': 'Language already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f'POST request failed: {str(e)}')
            return Response({
                'error': 'Language POST Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, language_id):
        try:
            language = self.get_object(language_id)
            if language is None:
                logger.info(f'PUT request failed: Language with ID {language_id} not found.')
                return Response({
                    'error': 'Language PUT Fail',
                    'detail': 'Language not found'
                }, status=status.HTTP_404_NOT_FOUND)

            language_serializer = LanguageSerializer(language, data=request.data)
            if language_serializer.is_valid():
                language_serializer.save()
                logger.info(f'Language with ID {language_id} updated successfully.')
                return Response({
                    'message': 'Language Update Success',
                    'data': language_serializer.data},
                    status=status.HTTP_200_OK
                )
            
            logger.warning(f'PUT request failed: Invalid data provided for Language ID {language_id}: {language_serializer.errors}')
            return Response({
                'error': 'Language PUT Fail',
                'detail': language_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except IntegrityError as e:
            logger.warning(f'PUT request failed: Language with ID {language_id} already exists.')
            return Response({
                'error': 'Language PUT Fail',
                'detail': 'Language already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f'PUT request failed: {str(e)}')
            return Response({
                'error': 'Language PUT Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, language_id):
        try:
            language = self.get_object(language_id)
            if language is None:
                logger.info(f'PATCH request failed: Language with ID {language_id} not found.')
                return Response({
                    'error': 'Language PATCH Fail',
                    'detail': 'Language not found'
                }, status=status.HTTP_404_NOT_FOUND)

            language_serializer = LanguageSerializer(language, data=request.data, partial=True)
            if language_serializer.is_valid():
                language_serializer.save()
                logger.info(f'Language with ID {language_id} partially updated successfully.')
                return Response({
                    'message': 'Language Partial Update Success',
                    'data': language_serializer.data},
                    status=status.HTTP_200_OK
                )

            logger.warning(f'PATCH request failed: Invalid data provided for Language ID {language_id}: {language_serializer.errors}')
            return Response({
                'error': 'Language PATCH Fail',
                'detail': language_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except IntegrityError as e:
            logger.warning(f'PATCH request failed: Language with ID {language_id} already exists.')
            return Response({
                'error': 'Language PATCH Fail',
                'detail': 'Language already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f'PATCH request failed: {str(e)}')
            return Response({
                'error': 'Language PATCH Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, language_id):
        try:
            language = self.get_object(language_id)
            if language is None:
                logger.info(f'DELETE request failed: Language with ID {language_id} not found.')
                return Response({
                    'error': 'Language DELETE Fail',
                    'detail': 'Language not found'
                }, status=status.HTTP_404_NOT_FOUND)

            language.delete()
            logger.info(f'Language with ID {language_id} deleted successfully.')
            return Response({
                'message': 'Language Delete Success'
                },
                status=status.HTTP_204_NO_CONTENT
            )
        
        except Exception as e:
            logger.error(f'DELETE request failed: {str(e)}')
            return Response({
                'error': 'Language DELETE Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)