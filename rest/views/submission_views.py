from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ..models import Problem, Language, InitCode, Submission, SubmissionDetail
from ..serializers import *
import logging

logger = logging.getLogger('rest')

# submission-crud
class SubmissionBasicView(APIView):
    def get(self, request):
        try:
            logger.info("Submission list retrieval request initiated")

            # Retrieve all submissions, ordered by the submitted_at timestamp
            submissions = Submission.objects.all().order_by('-submitted_at')
            submission_serializer = SubmissionSerializer(submissions, many=True, context={'exclude_submission_detail': True})
            logger.info(f"Submission list retrieval successful: {len(submission_serializer.data)} submissions found")

            return Response({
                'message': f'Submission List Retrieval Success : {len(submission_serializer.data)} submission(s) found',
                'data': submission_serializer.data},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Unexpected error during submission list retrieval: {str(e)}", exc_info=True)
            return Response({
                'error': 'Submission List GET Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        try:
            logger.info("New submission creation request initiated")

            data = request.data
            
            # Validate that the referenced user, problem, and language exist
            user_id = data.get('user_id')
            problem_id = data.get('problem_id')
            language_id = data.get('language_id')

            if not User.objects.filter(id=user_id).exists():
                logger.warning(f"User with ID {user_id} does not exist")
                return Response({
                    'error': 'Submissions POST Fail',
                    'detail': f'User with id {user_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            if not Problem.objects.filter(id=problem_id).exists():
                logger.warning(f"Problem with ID {problem_id} does not exist")
                return Response({
                    'error': 'Submissions POST Fail',
                    'detail': f'Problem with id {problem_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            if not Language.objects.filter(id=language_id).exists():
                logger.warning(f"Language with ID {language_id} does not exist")
                return Response({
                    'error': 'Submissions POST Fail',
                    'detail': f'Language with id {language_id} does not exist'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Proceed with normal serializer validation and saving
            submission_detail = data.pop('submission_detail', None)
            submission_serializer = SubmissionSerializer(data=data)

            if submission_serializer.is_valid():
                submission = submission_serializer.save()
                logger.debug(f"Submission record created with ID: {submission.id}")

                if submission_detail:
                    submission_detail['submission_id'] = submission.id
                    submission_detail_serializer = SubmissionDetailSerializer(data=submission_detail)
                    
                    if submission_detail_serializer.is_valid():
                        submission_detail_serializer.save()
                        logger.debug(f"SubmissionDetail record created for submission ID: {submission.id}")
                    else:
                        submission.delete()
                        logger.warning(f"SubmissionDetail validation failed for submission ID: {submission.id}")
                        return Response({
                            'error': 'Submissions POST Fail',
                            'detail': submission_detail_serializer.errors
                        }, status=status.HTTP_400_BAD_REQUEST)

                response_data = submission_serializer.data
                response_data['submission_detail'] = submission_detail_serializer.data
                logger.info(f"New submission added successfully with ID: {submission.id}")

                return Response({
                    'message': 'New Submission Addition Success',
                    'data': response_data},
                    status=status.HTTP_201_CREATED
                )

            logger.warning(f"Submission validation failed: {submission_serializer.errors}")
            return Response({
                'error': 'Submissions POST Fail',
                'detail': submission_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Unexpected error during submission creation: {str(e)}", exc_info=True)
            return Response({
                'error': 'Submissions POST Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SubmissionDetailView(APIView):
    # Helper method to get the Submission object
    def get_object(self, submission_id):
        try:
            logger.debug(f"Attempting to retrieve submission with ID: {submission_id}")
            return Submission.objects.select_related('submission_detail', 'user_id', 'problem_id', 'language_id').get(id=submission_id)
        except Submission.DoesNotExist:
            logger.warning(f"Submission with ID {submission_id} does not exist")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while retrieving submission with ID {submission_id}: {str(e)}", exc_info=True)
            raise e

    def get(self, request, submission_id):
        try:
            logger.info(f"Retrieving details for submission ID: {submission_id}")
            submission = self.get_object(submission_id)
            if submission is None:
                return Response({
                    'error': 'Submission Detail GET Fail',
                    'detail': 'Submission not found'
                }, status=status.HTTP_404_NOT_FOUND)

            submission_detail = SubmissionDetail.objects.get(submission_id=submission_id)
            if submission_detail is None:
                logger.warning(f"SubmissionDetail not found for submission ID {submission_id}")
                return Response({
                    'error': 'Submission Detail GET Fail',
                    'detail': 'Submission Detail not found'
                }, status=status.HTTP_404_NOT_FOUND)

            submission_serializer = SubmissionSerializer(submission) 
            submission_detail_serializer = SubmissionDetailSerializer(submission_detail)

            response_data = submission_serializer.data
            response_data['submission_detail'] = submission_detail_serializer.data

            logger.info(f"Submission details retrieval success for submission ID {submission_id}")
            return Response({
                'message': 'One Submission Retrieval Success',
                'data': response_data},
                status=status.HTTP_200_OK
            )
        
        except Exception as e:
            logger.error(f"Unexpected error during submission details retrieval for submission ID {submission_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Submission Detail GET Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, submission_id):
        try:
            logger.info(f"Updating submission with ID: {submission_id}")
            submission = self.get_object(submission_id)
            if submission is None:
                return Response({
                    'error': 'Submission Detail PUT Fail',
                    'detail': 'Submission not found'
                }, status=status.HTTP_404_NOT_FOUND)

            data = request.data
            if 'submission_detail' not in data:
                logger.warning("SubmissionDetail data is missing in the request")
                return Response({
                    'error': 'Submission Detail PUT Fail',
                    'detail': 'SubmissionDetail data is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            submission_detail_data = data.pop('submission_detail', None)
            submission_serializer = SubmissionSerializer(submission, data=data)

            if submission_serializer.is_valid():
                submission_serializer.save()

                if submission_detail_data:
                    try:
                        submission_detail = SubmissionDetail.objects.get(submission_id=submission_id)
                        submission_detail_data['submission_id'] = submission_id
                        submission_detail_serializer = SubmissionDetailSerializer(submission_detail, data=submission_detail_data)
                    
                        if submission_detail_serializer.is_valid():
                            submission_detail_serializer.save()
                            logger.info(f"SubmissionDetail updated successfully for submission ID {submission_id}")
                        else:
                            logger.warning(f"SubmissionDetail validation failed for submission ID {submission_id}")
                            return Response({
                                'error': 'Submission Detail PUT Fail',
                                'detail': submission_detail_serializer.errors
                            }, status=status.HTTP_400_BAD_REQUEST)
                    except SubmissionDetail.DoesNotExist:
                        logger.warning(f"SubmissionDetail not found for submission ID {submission_id}")
                        return Response({
                            'error': 'Submission Detail PUT Fail',
                            'detail': f'SubmissionDetail for submission {submission_id} is not found'
                        }, status=status.HTTP_404_NOT_FOUND)

                response_data = submission_serializer.data
                response_data['submission_detail'] = submission_detail_serializer.data

                logger.info(f"Submission update success for submission ID {submission_id}")
                return Response({
                    'message': 'One Submission Update Success',
                    'data': response_data
                    }, status=status.HTTP_200_OK
                )
            
            logger.warning(f"Submission validation failed for submission ID {submission_id}: {submission_serializer.errors}")
            return Response({
                'error': 'Submission Detail PUT Fail',
                'detail': submission_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except Exception as e:
            logger.error(f"Unexpected error during submission update for submission ID {submission_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Submission Detail PUT Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, submission_id):
        try:
            logger.info(f"Partially updating submission with ID: {submission_id}")
            submission = self.get_object(submission_id)
            if submission is None:
                return Response({
                    'error': 'Submission Detail PATCH Fail',
                    'detail': 'Submission not found'
                }, status=status.HTTP_404_NOT_FOUND)

            data = request.data
            submission_detail_data = data.pop('submission_detail', None)
            submission_serializer = SubmissionSerializer(submission, data=data, partial=True)

            if submission_serializer.is_valid():
                submission_serializer.save()

                if submission_detail_data:
                    try:
                        submission_detail = SubmissionDetail.objects.get(submission_id=submission_id)
                        submission_detail_data['submission_id'] = submission_id
                        submission_detail_serializer = SubmissionDetailSerializer(submission_detail, data=submission_detail_data, partial=True)
                    
                        if submission_detail_serializer.is_valid():
                            submission_detail_serializer.save()
                            logger.info(f"SubmissionDetail partially updated successfully for submission ID {submission_id}")
                        else:
                            logger.warning(f"SubmissionDetail validation failed during partial update for submission ID {submission_id}")
                            return Response({
                                'error': 'Submission Detail PATCH Fail',
                                'detail': submission_detail_serializer.errors
                            }, status=status.HTTP_400_BAD_REQUEST)
                    except SubmissionDetail.DoesNotExist:
                        logger.warning(f"SubmissionDetail not found for submission ID {submission_id}")
                        return Response({
                            'error': 'Submission Detail PATCH Fail',
                            'detail': f'SubmissionDetail for submission {submission_id} is not found'
                        }, status=status.HTTP_404_NOT_FOUND)

                response_data = submission_serializer.data
                response_data['submission_detail'] = submission_detail_serializer.data

                logger.info(f"Submission partial update success for submission ID {submission_id}")
                return Response({
                    'message': 'One Submission Partial Update Success',
                    'data': response_data
                    }, status=status.HTTP_200_OK
                )
            
            logger.warning(f"Submission validation failed during partial update for submission ID {submission_id}: {submission_serializer.errors}")
            return Response({
                'error': 'Submission Detail PATCH Fail',
                'detail': submission_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except Exception as e:
            logger.error(f"Unexpected error during submission partial update for submission ID {submission_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Submission Detail PATCH Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, submission_id):
        try:
            logger.info(f"Deleting submission with ID: {submission_id}")
            try:
                submission = Submission.objects.get(id=submission_id)
            except Submission.DoesNotExist:
                logger.warning(f"Submission with ID {submission_id} not found")
                return Response({
                    'error': 'Submission Detail DELETE Fail',
                    'detail': 'Submission not found'
                }, status=status.HTTP_404_NOT_FOUND)

            try:
                submission_detail = SubmissionDetail.objects.get(submission_id=submission_id)
                submission_detail.delete()
                logger.debug(f"SubmissionDetail for submission ID {submission_id} deleted successfully")
            except SubmissionDetail.DoesNotExist:
                logger.warning(f"SubmissionDetail for submission ID {submission_id} not found")
                return Response({
                    'error': 'Submission Detail DELETE Fail',
                    'detail': f'SubmissionDetail for submission {submission_id} is not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            submission.delete()
            logger.info(f"Submission with ID {submission_id} deleted successfully")
            return Response({
                'message': 'Submission Delete Success'
                },
                status=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            logger.error(f"Unexpected error during submission deletion for submission ID {submission_id}: {str(e)}", exc_info=True)
            return Response({
                'error': 'Submission Detail DELETE Fail',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)