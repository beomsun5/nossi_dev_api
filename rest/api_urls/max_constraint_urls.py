from django.urls import path
from ..views.problem_views import *
from ..views.max_constraint_views import *

urlpatterns = [
    path('', CodeJudgeMaxConstraintView.as_view(), name='code-judge-max-constraint'),
]
