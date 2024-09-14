from django.urls import path
from ..views.problem_views import *
from ..views.max_constraint_views import *

urlpatterns = [
    path('', ProblemListView.as_view(), name='problem-list'),
    path('tasks/<str:task_id>/', code_judge_task_status, name='code-judge-task-status'),
    path('<int:problem_id>/', ProblemDetailView.as_view(), name='problem-detail'),
    path('<int:problem_id>/code/', ProblemLangCodeView.as_view(), name='problem-lang-code'),
    path('<int:problem_id>/testcase/', ProblemTestcaseView.as_view(), name='problem-testcase'),
    path('<int:problem_id>/run/', problem_run, name='problem-run'),
    path('<int:problem_id>/run/task/', problem_run_for_task, name='problem-run-for-task'),
    path('<int:problem_id>/submit/', problem_submit, name='problem-submit'),
    path('<int:problem_id>/submit/task/', problem_submit_for_task, name='problem-submit-for-task'),
    path('<int:problem_id>/submissions/', get_problem_submission_list, name='problem-submission-list'),
    path('<int:problem_id>/submissions/<int:submission_id>/', get_problem_submission_detail, name='problem-submission-detail'),
]
