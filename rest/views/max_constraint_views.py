from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import IntegrityError
from ..models import *
from ..serializers import *
import logging

logger = logging.getLogger('rest')

class CodeJudgeMaxConstraintView(APIView):
    
    def get(self, request):
        try:
            language_id = request.query_params.get('language_id')
            problem_id = request.query_params.get('problem_id')
            
            logger.info(f"Received GET request for CodeJudgeMaxConstraint with problem ID {problem_id} and language ID {language_id}.")
            
            if language_id:
                language = Language.objects.filter(id=language_id).first()
                if language is None:
                    logger.warning(f"Invalid Language ID: {language_id} does not exist.")
                    return Response({
                        'error': 'Code Judge Max Constraint GET Fail',
                        'detail': 'Invalid Language ID - Language corresponding to given language id does not exist in DB'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            if problem_id:
                problem = Problem.objects.filter(id=problem_id).first()
                if problem is None:
                    logger.warning(f"Invalid Problem ID: {problem_id} does not exist.")
                    return Response({
                        'error': 'Code Judge Max Constraint GET Fail',
                        'detail': 'Invalid Problem ID - Problem corresponding to given problem id does not exist in DB'
                    }, status=status.HTTP_400_BAD_REQUEST)

            if problem_id and language_id:
                logger.debug(f"Retrieving specific CodeJudgeMaxConstraint for problem ID {problem_id} and language ID {language_id}.")
                max_constraint = CodeJudgeMaxConstraint.objects.filter(problem_id=problem_id, language_id=language_id).first()
                if max_constraint is None:
                    logger.warning(f"Max Constraints do not exist for problem ID {problem_id} and language ID {language_id}.")
                    return Response({
                        'error': 'Code Judge Max Constraint Detail GET Fail',
                        'detail': 'Max Constraints do not exist in DB'
                    }, status=status.HTTP_404_NOT_FOUND)

                serializer = CodeJudgeMaxConstraintSerializer(max_constraint)
                logger.info("Code Judge Max Constraint Retrieval Success")
                return Response({
                    'message': 'Code Judge Max Constraint Retrieval Success',
                    'data': serializer.data},
                    status=status.HTTP_200_OK
                )
            elif language_id:
                logger.debug(f"Filtering CodeJudgeMaxConstraints by language ID {language_id}.")
                max_constraint = CodeJudgeMaxConstraint.objects.filter(language_id=language_id)
                max_constraint_serializer = CodeJudgeMaxConstraintSerializer(max_constraint, many=True)
                logger.info("Code Judge Max Constraint retrieved successfully for the language filter.")
                return Response({
                    'message': 'Code Judge Max Constraint Retrieval Success - Filtered by language',
                    'data': max_constraint_serializer.data
                }, status=status.HTTP_200_OK)
            elif problem_id:
                logger.debug(f"Filtering CodeJudgeMaxConstraints by problem ID {problem_id}.")
                max_constraint = CodeJudgeMaxConstraint.objects.filter(problem_id=problem_id)
                max_constraint_serializer = CodeJudgeMaxConstraintSerializer(max_constraint, many=True)
                logger.info("Code Judge Max Constraint retrieved successfully for the problem filter.")
                return Response({
                    'message': 'Code Judge Max Constraint Retrieval Success - Filtered by problem',
                    'data': max_constraint_serializer.data
                }, status=status.HTTP_200_OK)
            else:
                logger.debug("Retrieving all CodeJudgeMaxConstraints.")
                constraints = CodeJudgeMaxConstraint.objects.all()
                max_constraint_serializer = CodeJudgeMaxConstraintSerializer(constraints, many=True)
                logger.info("All Code Judge Max Constraints Retrieval Success")
                return Response({
                    'message': 'Code Judge Max Constraint List Retrieval Success',
                    'data': max_constraint_serializer.data},
                    status=status.HTTP_200_OK
                )
        
        except Exception as e:
            logger.error(f"Unexpected error during GET request: {str(e)}", exc_info=True)
            return Response({
                'error': 'Code Judge Max Constraint GET Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            logger.info("Received POST request for CodeJudgeMaxConstraint.")
            max_constraint_serializer = CodeJudgeMaxConstraintSerializer(data=request.data)
            if max_constraint_serializer.is_valid():
                max_constraint_serializer.save()
                logger.info("New Code Judge Max Constraint added successfully.")
                return Response({
                    'message': 'New Code Judge Max Constraint Addition Success',
                    'data': max_constraint_serializer.data},
                    status=status.HTTP_201_CREATED
                )
            logger.warning("Validation failed for Code Judge Max Constraint POST request.")
            return Response({
                'error': 'Code Judge Max Constraint POST Fail',
                'detail': max_constraint_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except IntegrityError as e:
            logger.warning("Attempted to add a duplicate Max Constraint.")
            return Response({
                'error': 'Code Judge Max Constraint POST Fail',
                'detail': 'Already existing Max Constraint'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Unexpected error during POST request: {str(e)}", exc_info=True)
            return Response({
                'error': 'Code Judge Max Constraint POST Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request):
        try:
            language_id = request.query_params.get('language_id')
            problem_id = request.query_params.get('problem_id')

            logger.info(f"Received PUT request for CodeJudgeMaxConstraint with problem ID {problem_id} and language ID {language_id}.")
            
            language = Language.objects.filter(id=language_id).first()
            if language is None:
                logger.warning(f"Invalid Language ID: {language_id} does not exist.")
                return Response({
                    'error': 'Code Judge Max Constraint PUT Fail',
                    'detail': 'Invalid Language ID - Language corresponding to given language id does not exist in DB'
                }, status=status.HTTP_400_BAD_REQUEST)
        
            problem = Problem.objects.filter(id=problem_id).first()
            if problem is None:
                logger.warning(f"Invalid Problem ID: {problem_id} does not exist.")
                return Response({
                    'error': 'Code Judge Max Constraint PUT Fail',
                    'detail': 'Invalid Problem ID - Problem corresponding to given problem id does not exist in DB'
                }, status=status.HTTP_400_BAD_REQUEST)

            max_constraint = CodeJudgeMaxConstraint.objects.filter(problem_id=problem_id, language_id=language_id).first()
            if max_constraint is None:
                logger.warning(f"Max Constraint not found for problem ID {problem_id} and language ID {language_id}.")
                return Response({
                    'error': 'Code Judge Max Constraint PUT Fail',
                    'detail': 'Constraint not found'
                }, status=status.HTTP_404_NOT_FOUND)

            max_constraint_serializer = CodeJudgeMaxConstraintSerializer(max_constraint, data=request.data)
            if max_constraint_serializer.is_valid():
                max_constraint_serializer.save()
                logger.info(f"Code Judge Max Constraint updated successfully for problem ID {problem_id} and language ID {language_id}.")
                return Response({
                    'message': 'Code Judge Max Constraint Update Success',
                    'data': max_constraint_serializer.data},
                    status=status.HTTP_200_OK
                )
            
            logger.warning(f"Validation failed for Code Judge Max Constraint PUT request: {max_constraint_serializer.errors}")
            return Response({
                'error': 'Code Judge Max Constraint PUT Fail',
                'detail': max_constraint_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except IntegrityError as e:
            logger.warning("Attempted to update with a duplicate Max Constraint.")
            return Response({
                'error': 'Code Judge Max Constraint PUT Fail',
                'detail': 'Constraint already exists'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Unexpected error during PUT request: {str(e)}", exc_info=True)
            return Response({
                'error': 'Code Judge Max Constraint PUT Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request):
        try:
            language_id = request.query_params.get('language_id')
            problem_id = request.query_params.get('problem_id')
            
            logger.info(f"Received PATCH request for CodeJudgeMaxConstraint with problem ID {problem_id} and language ID {language_id}.")
            
            language = Language.objects.filter(id=language_id).first()
            if language is None:
                logger.warning(f"Invalid Language ID: {language_id} does not exist.")
                return Response({
                    'error': 'Code Judge Max Constraint PATCH Fail',
                    'detail': 'Invalid Language ID - Language corresponding to given language id does not exist in DB'
                }, status=status.HTTP_400_BAD_REQUEST)

            problem = Problem.objects.filter(id=problem_id).first()
            if problem is None:
                logger.warning(f"Invalid Problem ID: {problem_id} does not exist.")
                return Response({
                    'error': 'Code Judge Max Constraint PATCH Fail',
                    'detail': 'Invalid Problem ID - Problem corresponding to given problem id does not exist in DB'
                }, status=status.HTTP_400_BAD_REQUEST)

            max_constraint = CodeJudgeMaxConstraint.objects.filter(problem_id=problem_id, language_id=language_id).first()
            if max_constraint is None:
                logger.warning(f"Requested Max Constraint does not exist for problem ID {problem_id} and language ID {language_id}.")
                return Response({
                    'error': 'Code Judge Max Constraint PATCH Fail',
                    'detail': 'Requested Max Constraints do not exist'
                }, status=status.HTTP_404_NOT_FOUND)

            max_constraint_serializer = CodeJudgeMaxConstraintSerializer(max_constraint, data=request.data, partial=True)
            if max_constraint_serializer.is_valid():
                max_constraint_serializer.save()
                logger.info(f"Code Judge Max Constraint partially updated successfully for problem ID {problem_id} and language ID {language_id}.")
                return Response({
                    'message': 'Code Judge Max Constraint Partial Update Success',
                    'data': max_constraint_serializer.data},
                    status=status.HTTP_200_OK
                )

            logger.warning(f"Validation failed for Code Judge Max Constraint PATCH request: {max_constraint_serializer.errors}")
            return Response({
                'error': 'Code Judge Max Constraint PATCH Fail',
                'detail': max_constraint_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except IntegrityError as e:
            logger.warning("Attempted to partially update with a duplicate Max Constraint.")
            return Response({
                'error': 'Constraint PATCH Fail',
                'detail': 'Already existing Max Constraint'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Unexpected error during PATCH request: {str(e)}", exc_info=True)
            return Response({
                'error': 'Constraint PATCH Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        try:
            language_id = request.query_params.get('language_id')
            problem_id = request.query_params.get('problem_id')
            
            logger.info(f"Received DELETE request for CodeJudgeMaxConstraint with problem ID {problem_id} and language ID {language_id}.")
            
            language = Language.objects.filter(id=language_id).first()
            if language is None:
                logger.warning(f"Invalid Language ID: {language_id} does not exist.")
                return Response({
                    'error': 'Code Judge Max Constraint DELETE Fail',
                    'detail': 'Invalid Language ID - Language corresponding to given language id does not exist in DB'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            problem = Problem.objects.filter(id=problem_id).first()
            if problem is None:
                logger.warning(f"Invalid Problem ID: {problem_id} does not exist.")
                return Response({
                    'error': 'Code Judge Max Constraint DELETE Fail',
                    'detail': 'Invalid Problem ID - Problem corresponding to given problem id does not exist in DB'
                }, status=status.HTTP_400_BAD_REQUEST)

            max_constraint = CodeJudgeMaxConstraint.objects.filter(problem_id=problem_id, language_id=language_id).first()
            if max_constraint is None:
                logger.warning(f"Max Constraint does not exist for problem ID {problem_id} and language ID {language_id}.")
                return Response({
                    'error': 'Code Judge Max Constraint DELETE Fail',
                    'detail': 'Requested Max Constraints do not exist'
                }, status=status.HTTP_404_NOT_FOUND
                )

            max_constraint.delete()
            logger.info(f"Code Judge Max Constraint deleted successfully for problem ID {problem_id} and language ID {language_id}.")
            return Response({
                'message': 'Code Judge Max Constraint Delete Success'
                },
                status=status.HTTP_204_NO_CONTENT
            )
        
        except Exception as e:
            logger.error(f"Unexpected error during DELETE request: {str(e)}", exc_info=True)
            return Response({
                'error': 'Code Judge Max Constraint DELETE Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)