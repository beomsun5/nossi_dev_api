from django.contrib import admin
from .models import User, Profile, Job, Like, Bookmark, Category, Problem, ProblemMeta, Language, InitCode, Editorial, Submission, SubmissionDetail, Solution, Comment

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'is_active', 'is_staff', 'is_superuser', 'provider')
    search_fields = ('username', 'email')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'provider')
    ordering = ('-join_date',)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'real_name', 'gender', 'date_of_birth', 'job', 'role')
    search_fields = ('user_id__username', 'real_name')
    list_filter = ('gender', 'role')

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('job_name',)
    search_fields = ('job_name',)

@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'problem_id', 'created_at')
    search_fields = ('user_id__username', 'problem_id__title')

@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'problem_id', 'created_at')
    search_fields = ('user_id__username', 'problem_id__title')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('category_name', 'description')
    search_fields = ('category_name',)
    ordering = ('category_name',)

@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    list_display = ('title', 'level', 'attempt_number', 'solve_number', 'created_at')
    search_fields = ('title',)
    list_filter = ('level',)
    ordering = ('-created_at',)

@admin.register(ProblemMeta)
class ProblemMetaAdmin(admin.ModelAdmin):
    list_display = ('problem_id', 'description', 'constraints')

@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('language',)
    search_fields = ('language',)

@admin.register(InitCode)
class InitCodeAdmin(admin.ModelAdmin):
    list_display = ('problem_id', 'language_id', 'template_code')
    search_fields = ('problem_id__title', 'language_id__language')

@admin.register(Editorial)
class EditorialAdmin(admin.ModelAdmin):
    list_display = ('description',)

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'problem_id', 'final_result', 'submitted_at')
    list_filter = ('final_result',)
    search_fields = ('user_id__username', 'problem_id__title')
    ordering = ('-submitted_at',)

@admin.register(SubmissionDetail)
class SubmissionDetailAdmin(admin.ModelAdmin):
    list_display = ('submission_id', 'testcase_id', 'submission_result')
    search_fields = ('submission_id__id', 'testcase_id')

@admin.register(Solution)
class SolutionAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'problem_id', 'title', 'view_count', 'created_at')
    search_fields = ('title', 'user_id__username', 'problem_id__title')
    ordering = ('-created_at',)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'solution_id', 'content', 'created_at')
    search_fields = ('user_id__username', 'solution_id__title')
    ordering = ('-created_at',)