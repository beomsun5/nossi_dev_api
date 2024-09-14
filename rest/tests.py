from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from .models import User, Problem, Language, Submission, SubmissionDetail
from .serializers import SubmissionSerializer, SubmissionDetailSerializer

class SubmissionBasicViewTests(APITestCase):
    def setUp(self):
        # Create test users, problems, and languages
        self.user = User.objects.create_user(username='testuser', email='testuser@example.com', password='testpass')
        self.problem = Problem.objects.create(title="Sample Problem", categories="Math, Addition", level=2)
        self.language = Language.objects.create(language="python")

        # Create initial submission for GET method testing
        self.submission = Submission.objects.create(
            user_id=self.user,
            problem_id=self.problem,
            language_id=self.language,
            final_result='SOLVED',
            submitted_code='print(1+1)',
            passed_num=1,
            total_num=1
        )
        self.submission_detail = SubmissionDetail.objects.create(
            submission_id=self.submission,
            testcase_id='1',
            submission_result='SOLVED',
            run_time='0.1',
            memory='256'
        )

        # URLs for testing
        self.url = reverse('submission-basic')

    def test_get_submissions(self):
        # Send GET request
        response = self.client.get(self.url)

        # Check the response status code and data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('data', response.data)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['final_result'], 'SOLVED')

    def test_post_submission_success(self):
        # Prepare data for POST request
        post_data = {
            'user_id': self.user.id,
            'problem_id': self.problem.id,
            'language_id': self.language.id,
            'final_result': 'SOLVED',
            'submitted_code': 'print(2+2)',
            'passed_num': 1,
            'total_num': 1,
            'submission_detail': {
                'testcase_id': ['1'],
                'submission_result': ['SOLVED'],
                'run_time': ['0.2'],
                'memory': ['128']
            }
        }

        # Send POST request
        response = self.client.post(self.url, data=post_data, format='json')

        # Check the response status code and data
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('data', response.data)
        self.assertEqual(response.data['data']['final_result'], 'SOLVED')
        self.assertEqual(response.data['data']['submission_detail']['testcase_id'], ['1'])

    def test_post_submission_fail_user_does_not_exist(self):
        # Prepare data with a non-existent user_id
        post_data = {
            'user_id': 9999,  # Non-existent user_id
            'problem_id': self.problem.id,
            'language_id': self.language.id,
            'final_result': 'SOLVED',
            'submitted_code': 'print(2+2)',
            'passed_num': 1,
            'total_num': 1
        }

        # Send POST request
        response = self.client.post(self.url, data=post_data, format='json')

        # Check the response status code and data
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('User with id 9999 does not exist', response.data['detail'])

    def test_post_submission_fail_problem_does_not_exist(self):
        # Prepare data with a non-existent problem_id
        post_data = {
            'user_id': self.user.id,
            'problem_id': 9999,  # Non-existent problem_id
            'language_id': self.language.id,
            'final_result': 'SOLVED',
            'submitted_code': 'print(2+2)',
            'passed_num': 1,
            'total_num': 1
        }

        # Send POST request
        response = self.client.post(self.url, data=post_data, format='json')

        # Check the response status code and data
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Problem with id 9999 does not exist', response.data['detail'])

    def test_post_submission_fail_language_does_not_exist(self):
        # Prepare data with a non-existent language_id
        post_data = {
            'user_id': self.user.id,
            'problem_id': self.problem.id,
            'language_id': 9999,  # Non-existent language_id
            'final_result': 'SOLVED',
            'submitted_code': 'print(2+2)',
            'passed_num': 1,
            'total_num': 1
        }

        # Send POST request
        response = self.client.post(self.url, data=post_data, format='json')

        # Check the response status code and data
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Language with id 9999 does not exist', response.data['detail'])

    def tearDown(self):
        # Clean up created data
        self.submission_detail.delete()
        self.submission.delete()
        self.language.delete()
        self.problem.delete()
        self.user.delete()