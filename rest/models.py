from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.cache import cache
from django_redis import get_redis_connection
from .managers import UserManager
from .utils import *


# Create your models here.
class User(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=100, unique=True, null=False, blank=False)
    email = models.EmailField(null=False, blank=False)
    email_verified = models.BooleanField(default=False)
    password = models.CharField(max_length=255, null=True, blank=True)
    is_staff = models.BooleanField(default=False)  # 슈퍼유저 권한
    is_superuser = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)  # 계정 활성화 상태
    social_uid = models.BigIntegerField(
        null=True, unique=True, blank=False
    ) # 소셜 로그인으로 얻는 사용자의 user_id
    provider = models.CharField(max_length=255, null=True, blank=True)
    provider_id = models.CharField(max_length=255, null=True, blank=True)
    refresh_token = models.TextField(null=True, blank=True)
    rt_expire = models.DateTimeField(null=True, blank=True)
    join_date = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    objects = UserManager()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

    class Meta:
        indexes = [
            models.Index(fields=['email'])
        ]

class Profile(models.Model):
    user_id = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    profile_image = models.URLField(max_length=200, blank=True)
    real_name = models.CharField(max_length=50, null=True, blank=True)
    gender = models.CharField(max_length=7, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    job = models.ForeignKey('Job', on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=10, default="user")

# Job
class Job(models.Model):
    job_name = models.CharField(max_length=50, default='None')

# Like
class Like(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    problem_id = models.ForeignKey('Problem', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user_id', 'problem_id',)

# Bookmark
class Bookmark(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    problem_id = models.ForeignKey('Problem', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user_id', 'problem_id',)

# Category
class Category(models.Model):
    category_name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(null=True, blank=True)

# Problem
class Problem(models.Model):
    title = models.CharField(max_length=255, unique=True, default="No Title")
    categories = models.TextField()
    level = models.PositiveSmallIntegerField(default=1)  # Assuming level is 1-5
    attempt_number = models.BigIntegerField(default=0)
    solve_number = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    editorial_id = models.OneToOneField('Editorial', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=['-updated_at'])
        ]

    def invalidate_problem_list_cache(self):
        # Invalidate cache for anonymous users
        cache.delete(generate_problem_list_cache_key(None))

        # Invalidate cache for all users stored in Redis
        redis_conn = get_redis_connection("default")
        cached_user_ids = redis_conn.smembers("cached_users")

        for user_id in cached_user_ids:
            cache.delete(generate_problem_list_cache_key(user_id))

    def save(self, *args, **kwargs):
        # Invalidate the cache for both the problem list and problem details before saving
        self.invalidate_problem_list_cache()  # Invalidate problem list
        cache.delete(generate_problem_cache_key(self.pk))  # Invalidate specific problem
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Invalidate the cache for both the problem list and problem details before deleting
        self.invalidate_problem_list_cache()  # Invalidate problem list
        cache.delete(generate_problem_cache_key(self.pk))  # Invalidate specific problem
        super().delete(*args, **kwargs)


# Problem Meta
class ProblemMeta(models.Model):
    problem_id = models.OneToOneField('Problem', on_delete=models.CASCADE, primary_key=True)
    description = models.TextField(default='No Contents', null=True, blank=True)
    constraints = models.TextField(default='No Constraints', null=True, blank=True)
    testcase = models.JSONField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Invalidate the cache for the problem details before saving
        cache.delete(generate_problem_meta_cache_key(self.problem_id.pk))  # Invalidate problem meta
        cache.delete(generate_problem_cache_key(self.problem_id.pk))  # Invalidate specific problem
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Invalidate the cache for the problem details before deleting
        cache.delete(generate_problem_meta_cache_key(self.problem_id.pk))  # Invalidate problem meta
        cache.delete(generate_problem_cache_key(self.problem_id.pk))  # Invalidate specific problem
        super().delete(*args, **kwargs)

# Code Judge Max Constraint
class CodeJudgeMaxConstraint(models.Model):
    problem_id = models.ForeignKey('Problem', on_delete=models.CASCADE, db_index=True)
    language_id = models.ForeignKey('Language', on_delete=models.CASCADE, db_index=True)
    max_cpu_time = models.BigIntegerField(default=5000)
    max_real_time = models.BigIntegerField(default=15000)
    max_memory = models.BigIntegerField(default=256*1024*1024)

    class Meta:
        unique_together = ('problem_id', 'language_id',)

# Language
class Language(models.Model):
    language = models.CharField(max_length=10, unique=True, db_index=True)

# Init Code
class InitCode(models.Model):
    problem_id = models.ForeignKey(Problem, on_delete=models.CASCADE, related_name='init_codes')
    language_id = models.ForeignKey(Language, on_delete=models.CASCADE, related_name='init_codes')
    template_code = models.TextField(default='', null=True, blank=True)
    run_code = models.TextField(default='', null=True, blank=True)

    class Meta:
        unique_together = ('problem_id', 'language_id',)
        indexes = [
            models.Index(fields=['problem_id', 'language_id'])
        ]

# Editorial
class Editorial(models.Model):
    description = models.TextField(null=True, blank=True)

# Submission (Single Submission Information)
class Submission(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    problem_id = models.ForeignKey(Problem, on_delete=models.CASCADE)
    language_id = models.ForeignKey(Language, on_delete=models.CASCADE, default=1)
    final_result = models.TextField(default="WRONG")
    avg_run_time = models.BigIntegerField(default=0)
    avg_memory = models.BigIntegerField(default=0)
    submitted_code = models.TextField(null=True, blank=True)
    passed_num = models.IntegerField(default=0)
    total_num = models.IntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user_id', 'problem_id']),
            models.Index(fields=['-submitted_at'])
        ]

class SubmissionDetail(models.Model):
    submission_id = models.OneToOneField(Submission, on_delete=models.CASCADE, primary_key=True, related_name='submission_detail')
    testcase_id = models.TextField()
    submission_result = models.TextField()
    run_time = models.TextField()
    memory = models.TextField()

# Solution
class Solution(models.Model):
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    problem_id = models.ForeignKey(Problem, on_delete=models.CASCADE)
    categories = models.TextField(null=True, blank=True)
    view_count = models.IntegerField(default=0)
    title = models.CharField(max_length=255, default="No Title")
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # class Meta:
    #     indexes = [
    #         models.Index(fields=['-updated_at'])
    #     ]

# Comment
class Comment(models.Model):
    solution_id = models.ForeignKey(Solution, null=True, blank=True, on_delete=models.CASCADE)
    editorial_id = models.ForeignKey(Editorial, null=True, blank=True, on_delete=models.CASCADE)
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # class Meta:
    #     indexes = [
    #         models.Index(fields=['user_id', 'solution_id'])
    #         models.Index(fields=['user_id', 'editorial_id'])
    #         models.Index(fields=['-updated_at'])
    #     ]