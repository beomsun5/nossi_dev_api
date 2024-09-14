from .models import *
from rest_framework import serializers
from dj_rest_auth.registration.serializers import (
    RegisterSerializer as DefaultRegisterSerializer,
)

class UserRegisterSerializer(DefaultRegisterSerializer):
    def custom_signup(self, request, user):
        username = self.validated_data.pop("username")
        if username:
            user.username = username
            user.save()
            
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'

    def create(self, validated_data):
        user = User.objects.create_user(
            username = validated_data.get('username', 'Anonymous'),
            email = validated_data.get('email', 'example@none.com'),
            password = validated_data['password']
        )
        return user

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        exclude = ['user_id']  # Exclude the user_id field


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = '__all__'

class LikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Like
        fields = '__all__'

class BookmarkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bookmark
        fields = '__all__'

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ZipFileUploadSerializer(serializers.Serializer):
    testcase_zip = serializers.FileField()

    def validate_file(self, value):
        if not value.name.endswith('.zip'):
            raise serializers.ValidationError("Invalid file format. Only zip files are allowed.")
        return value

class ProblemRunRequestSerializer(serializers.Serializer):
    solution = serializers.CharField(style={'base_template': 'textarea.html'}, max_length=5000)
    testcase = serializers.JSONField()

class ProblemSubmitSerializer(serializers.Serializer):
    solution = serializers.CharField(style={'base_template': 'textarea.html'}, max_length=5000)

class ProblemMetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProblemMeta
        fields = '__all__'
        
    def create(self, validated_data):
        return super().create(validated_data)

    def update(self, instance, validated_data):
        instance.description = validated_data.get('description', instance.description)
        instance.constraints = validated_data.get('constraints', instance.constraints)
        instance.testcase = validated_data.get('testcase', instance.testcase)
        instance.save()
        return instance

class ProblemSerializer(serializers.ModelSerializer):
    categories = serializers.ListField(
        child=serializers.CharField(),  # Ensure each item in the list is a string
        write_only=True                 # This is to accept input as a list
    )
    solve_status = serializers.SerializerMethodField()

    class Meta:
        model = Problem
        fields = '__all__'

    def create(self, validated_data):
        categories_list = validated_data.pop('categories', [])
        validated_data['categories'] = ','.join(categories_list)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        categories_list = validated_data.pop('categories', [])
        validated_data['categories'] = ','.join(categories_list)
        return super().update(instance, validated_data)

    def get_solve_status(self, obj):
        user_id = self.context.get('user_id')
        
        if not user_id:
            return '풀이 미완'

        submissions = Submission.objects.filter(user_id=user_id, problem_id=obj.id)

        if not submissions.exists():
            return '풀이 미완'

        solved_submission = submissions.filter(final_result='SOLVED')
        if solved_submission.exists():
            return '풀이 완료'

        return '풀이 중'

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Ensure categories are included
        if hasattr(instance, 'categories'):
            categories_string = instance.categories
            representation['categories'] = categories_string.split(',') if categories_string else []
        else:
            representation['categories'] = []
        
        request_method = self.context.get('request').method if 'request' in self.context else None
        if request_method == 'GET':
            representation['solve_status'] = self.get_solve_status(instance)

        return representation

class CodeJudgeMaxConstraintSerializer(serializers.ModelSerializer):
    class Meta:
        model = CodeJudgeMaxConstraint
        fields = '__all__'

class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = '__all__'

class InitCodeSerializer(serializers.ModelSerializer):
    # Define problem_id and language_id as read-only fields
    problem_id = serializers.PrimaryKeyRelatedField(queryset=Problem.objects.all())
    language_id = serializers.PrimaryKeyRelatedField(queryset=Language.objects.all())

    class Meta:
        model = InitCode
        fields = ['problem_id', 'language_id', 'template_code', 'run_code']

    def create(self, validated_data):
        init_code = InitCode.objects.create(**validated_data)
        return init_code

    def update(self, instance, validated_data):
        # Only update template_code and run_code
        instance.template_code = validated_data.get('template_code', instance.template_code)
        instance.run_code = validated_data.get('run_code', instance.run_code)
        instance.save()
        return instance

class EditorialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Editorial
        fields = '__all__'

class SubmissionDetailSerializer(serializers.ModelSerializer):
    testcase_id = serializers.ListField(
        child=serializers.CharField(),  # Ensure each item in the list is a string
        write_only=True                 # This is to accept input as a list
    )
    submission_result = serializers.ListField(
        child=serializers.CharField(),  # Ensure each item in the list is a string
        write_only=True                 # This is to accept input as a list
    )
    run_time = serializers.ListField(
        child=serializers.CharField(),  # Ensure each item in the list is a string
        write_only=True                 # This is to accept input as a list
    )
    memory = serializers.ListField(
        child=serializers.CharField(),  # Ensure each item in the list is a string
        write_only=True                 # This is to accept input as a list
    )

    class Meta:
        model = SubmissionDetail
        fields = '__all__'

    def create(self, validated_data):
        # testcase_id
        testcase_id_list = validated_data.pop('testcase_id', [])
        validated_data['testcase_id'] = ','.join(testcase_id_list)
        # submission_result
        submission_result_list = validated_data.pop('submission_result', [])
        validated_data['submission_result'] = ','.join(submission_result_list)
        # run_time
        run_time_list = validated_data.pop('run_time', [])
        validated_data['run_time'] = ','.join(run_time_list)
        # memory
        memory_list = validated_data.pop('memory', [])
        validated_data['memory'] = ','.join(memory_list)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # testcase_id
        testcase_id_list = validated_data.pop('testcase_id', [])
        validated_data['testcase_id'] = ','.join(testcase_id_list)
        # submission_result
        submission_result_list = validated_data.pop('submission_result', [])
        validated_data['submission_result'] = ','.join(submission_result_list)
        # run_time
        run_time_list = validated_data.pop('run_time', [])
        validated_data['run_time'] = ','.join(run_time_list)
        # memory
        memory_list = validated_data.pop('memory_id', [])
        validated_data['memory'] = ','.join(memory_list)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        # Convert comma-separated strings back to lists for the API response
        representation = super().to_representation(instance)
        # testcase_id
        if hasattr(instance, 'testcase_id'):
            testcase_id_string = instance.testcase_id
            representation['testcase_id'] = testcase_id_string.split(',') if testcase_id_string else []
        else:
            representation['testcase_id'] = []
        
        # submission_result
        if hasattr(instance, 'submission_result'):
            submission_result_string = instance.submission_result
            representation['submission_result'] = submission_result_string.split(',') if submission_result_string else []
        else:
            representation['submission_result'] = []
        
        # run_time
        if hasattr(instance, 'run_time'):
            run_time_string = instance.run_time
            representation['run_time'] = run_time_string.split(',') if run_time_string else []
        else:
            representation['run_time'] = []
        
        # memory
        if hasattr(instance, 'memory'):
            memory_string = instance.memory
            representation['memory'] = memory_string.split(',') if memory_string else []
        else:
            representation['memory'] = []
        
        return representation


class SubmissionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Submission
        fields = '__all__'

    def create(self, validated_data):
        return Submission.objects.create(**validated_data)

    def update(self, instance, validated_data):
        instance.user_id = validated_data.get('user_id', instance.user_id)
        instance.problem_id = validated_data.get('problem_id', instance.problem_id)
        instance.language_id = validated_data.get('language_id', instance.language_id)
        instance.final_result = validated_data.get('final_result', instance.final_result)
        instance.submitted_code = validated_data.get('submitted_code', instance.submitted_code)
        instance.passed_num = validated_data.get('passed_num', instance.passed_num)
        instance.total_num = validated_data.get('total_num', instance.total_num)
        instance.save()
        
        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if self.context.get('exclude_submission_detail', False):
            representation.pop('submission_detail', None)
        return representation

class SolutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Solution
        fields = '__all__'

class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = '__all__'
