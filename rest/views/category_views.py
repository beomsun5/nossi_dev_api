from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ..models import Category
from ..serializers import CategorySerializer
from django.db import IntegrityError
import logging

logger = logging.getLogger('rest')

class CategoryView(APIView):
    # Helper method to get the Category object
    def get_object(self, category_id):
        try:
            return Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            logger.warning(f'Category with ID {category_id} does not exist.')
            return None
        except Exception as e:
            logger.error(f'Error fetching category with ID {category_id}: {str(e)}')
            raise e

    def get(self, request, category_id=None):
        try:
            if category_id:
                # Retrieve a specific category
                category = self.get_object(category_id)
                if category is None:
                    logger.info(f'GET request failed: Category with ID {category_id} not found.')
                    return Response({
                        'error': 'Category Detail GET Fail',
                        'detail': 'Category not found'
                    }, status=status.HTTP_404_NOT_FOUND)

                category_serializer = CategorySerializer(category)
                logger.info(f'Category with ID {category_id} retrieved successfully.')
                return Response({
                    'message': 'Category Retrieval Success',
                    'data': category_serializer.data},
                    status=status.HTTP_200_OK
                )
            else:
                # Retrieve all categories
                categories = Category.objects.all().order_by('category_name')
                category_serializer = CategorySerializer(categories, many=True)
                logger.info(f'All categories retrieved successfully. Count: {len(categories)}')
                return Response({
                    'message': 'Category List Retrieval Success',
                    'data': category_serializer.data},
                    status=status.HTTP_200_OK
                )
        
        except Exception as e:
            logger.error(f'GET request failed: {str(e)}')
            return Response({
                'error': 'Category GET Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            category_serializer = CategorySerializer(data=request.data)
            if category_serializer.is_valid():
                category_serializer.save()
                logger.info(f'New category added successfully: {category_serializer.data}')
                return Response({
                    'message': 'New Category Addition Success',
                    'data': category_serializer.data},
                    status=status.HTTP_201_CREATED
                )
            logger.warning(f'POST request failed: Invalid data provided: {category_serializer.errors}')
            return Response({
                'error': 'Category POST Fail',
                'detail': category_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except IntegrityError as e:
            logger.warning(f'POST request failed: Category already exists.')
            return Response({
                'error': 'Category POST Fail',
                'detail': 'Category already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f'POST request failed: {str(e)}')
            return Response({
                'error': 'Category POST Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, category_id):
        try:
            category = self.get_object(category_id)
            if category is None:
                logger.info(f'PUT request failed: Category with ID {category_id} not found.')
                return Response({
                    'error': 'Category PUT Fail',
                    'detail': 'Category not found'
                }, status=status.HTTP_404_NOT_FOUND)

            category_serializer = CategorySerializer(category, data=request.data)
            if category_serializer.is_valid():
                category_serializer.save()
                logger.info(f'Category with ID {category_id} updated successfully.')
                return Response({
                    'message': 'Category Update Success',
                    'data': category_serializer.data},
                    status=status.HTTP_200_OK
                )
            
            logger.warning(f'PUT request failed: Invalid data provided for Category ID {category_id}: {category_serializer.errors}')
            return Response({
                'error': 'Category PUT Fail',
                'detail': category_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except IntegrityError as e:
            logger.warning(f'PUT request failed: Category with ID {category_id} already exists.')
            return Response({
                'error': 'Category PUT Fail',
                'detail': 'Category already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f'PUT request failed: {str(e)}')
            return Response({
                'error': 'Category PUT Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, category_id):
        try:
            category = self.get_object(category_id)
            if category is None:
                logger.info(f'PATCH request failed: Category with ID {category_id} not found.')
                return Response({
                    'error': 'Category PATCH Fail',
                    'detail': 'Category not found'
                }, status=status.HTTP_404_NOT_FOUND)

            category_serializer = CategorySerializer(category, data=request.data, partial=True)
            if category_serializer.is_valid():
                category_serializer.save()
                logger.info(f'Category with ID {category_id} partially updated successfully.')
                return Response({
                    'message': 'Category Partial Update Success',
                    'data': category_serializer.data},
                    status=status.HTTP_200_OK
                )

            logger.warning(f'PATCH request failed: Invalid data provided for Category ID {category_id}: {category_serializer.errors}')
            return Response({
                'error': 'Category PATCH Fail',
                'detail': category_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except IntegrityError as e:
            logger.warning(f'PATCH request failed: Category with ID {category_id} already exists.')
            return Response({
                'error': 'Category PATCH Fail',
                'detail': 'Category already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f'PATCH request failed: {str(e)}')
            return Response({
                'error': 'Category PATCH Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, category_id):
        try:
            category = self.get_object(category_id)
            if category is None:
                logger.info(f'DELETE request failed: Category with ID {category_id} not found.')
                return Response({
                    'error': 'Category DELETE Fail',
                    'detail': 'Category not found'
                }, status=status.HTTP_404_NOT_FOUND
                )

            category.delete()
            logger.info(f'Category with ID {category_id} deleted successfully.')
            return Response({
                'message': 'Category Delete Success'
                },
                status=status.HTTP_204_NO_CONTENT
            )
        
        except Exception as e:
            logger.error(f'DELETE request failed: {str(e)}')
            return Response({
                'error': 'Category DELETE Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)