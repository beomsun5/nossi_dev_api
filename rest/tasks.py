from celery import shared_task
from .models import *
from .serializers import *
from django.db.models import F
from .code_judge_for_task.Judger import SubmissionDriver, Compiler, Judger
from .code_judge_for_task.config import lang_config, RUN_BASE_DIR, TESTCASE_BASE_DIR
import logging

logger = logging.getLogger('rest')

SUBMISSION_RESULT = {
    -2: "SOLVED",
    -1: "WRONG",
    1: "TIME_LIMIT_EXCEEDED",
    2: "TIME_LIMIT_EXCEEDED",
    3: "MEMORY_LIMIT_EXCEEDED",
    4: "RUNTIME_ERROR",
    5: "SYSTEM_ERROR",
}

@shared_task(bind=True)
def do_judge_for_task(
    self,
    language,
    main_code,
    user_code,
    testcase_dir_name,
    max_cpu_time,
    max_real_time,
    max_memory,
    ):
    try:
        logger.debug(f'Task {self.name} with ID {self.request.id} is running - Task Re-run Count : {self.request.retries}')
        logger.info(f"Judgement process initiated for language: {language}, testcase_dir_name: {testcase_dir_name}")

        language_config = lang_config[language]

        with SubmissionDriver(RUN_BASE_DIR, testcase_dir_name) as dirs:
            submission_dir, testcase_dir = dirs

            # Prepare source code paths based on language configuration
            if "compile" in language_config:
                main_src_path = os.path.join(submission_dir, language_config["compile"]["src_name"])
                user_src_path = os.path.join(submission_dir, language_config["compile"]["solution_name"])
            else:  # JS case
                main_src_path = os.path.join(submission_dir, language_config["run"]["exe_name"])
                user_src_path = os.path.join(submission_dir, language_config["run"]["solution_name"])

            logger.debug(f"Main source path: {main_src_path}, User source path: {user_src_path}")

            # Prepare user and main code
            try:
                with open(main_src_path, "w", encoding="utf-8") as f:
                    f.write(main_code)
                with open(user_src_path, "w", encoding="utf-8") as f:
                    f.write(user_code)
                    if language == "js":
                        f.write(r"""module.exports = { solution };""")
                logger.debug(f"User code and main code written to respective paths")
            except IOError as io_error:
                logger.error(f"Failed to write code files: {str(io_error)}", exc_info=True)
                raise

            # Compile phase
            compile_error_msg = ""
            try:
                if "compile" in language_config:
                    exe_path, compile_error_msg = Compiler().compile(
                        compile_config=language_config["compile"], src_path=main_src_path, output_dir=submission_dir
                    )
                else:  # JS case
                    exe_path = main_src_path

                logger.info(f"Compilation process completed. Executable path: {exe_path}")
            except Exception as e:
                logger.error(f"Compilation failed: {str(e)}", exc_info=True)
                raise

            if compile_error_msg or (language != "java" and not os.path.exists(exe_path)):
                logger.warning(f"Compilation error or executable not found for language: {language}, error: {compile_error_msg}")
                return None, compile_error_msg

            # Code Judgement Execution
            judge_client = Judger(
                run_config=language_config["run"],
                exe_path=exe_path,
                max_cpu_time=max_cpu_time,
                max_real_time=max_real_time,
                max_memory=max_memory,
                testcase_dir=testcase_dir,
                submission_dir=submission_dir
            )
            logger.info(f"Judgement client initialized for execution.")
            results = judge_client.run()

        logger.info(f"Judgement execution completed with results.")
        return results, compile_error_msg

    except Exception as e:
        logger.error(f"Task failed: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=5, max_retries=3)  # Retry the task up to 3 times with a 5-second delay


@shared_task
def create_submission_and_response_for_task(**kwargs):
    try:
        logger.info(f"Creating submission record for user: {kwargs.get('user_id')} and problem: {kwargs.get('problem_id')}")

        # Parameters
        user = User.objects.get(id=kwargs.get('user_id'))
        problem = Problem.objects.get(id=kwargs.get('problem_id'))
        language = Language.objects.get(id=kwargs.get('language_id'))
        judge_result = kwargs.get('judge_result')
        compile_error_msg = kwargs.get('compile_error_msg')
        user_code = kwargs.get('user_code')
        
        """
        Create Submission Record
        """
        submission = Submission.objects.create(
            user_id=user,
            problem_id=problem,
            language_id=language,
            submitted_code=user_code
        )
        submission_id = submission.id
        logger.debug(f"Submission record created with ID: {submission_id}")
        
        testcase_ids = []
        submission_results = []
        run_times = []
        memories = []
        submission_detail_response = []     # Response Data
        passed_num = 0                      # Solved Problem Number
        total_num = len(judge_result)      # Total Problem Number
        final_result = -2                   # Final Result of the submission
        problem_is_solved = True
        avg_run_time = 0
        avg_memory = 0

        """
        Organize Submission & SubmissionDetail
        """
        for result in judge_result:
            # SOLVED == -2 / WRONG == -1
            result['result'] = -2 if result['result'] == 0 else result['result']
            testcase_result = SUBMISSION_RESULT.get(result['result'], "")
            testcase_id = result['testcase']
            if not testcase_result:
                logger.error(f"[Organize Submission] Unexpected Submission result - {testcase_id} testcase result : {testcase_result}")
                raise ValueError(f'[Organize Submission] Unexpected Submission result - {testcase_id} testcase result : {testcase_result}')

            submission_detail = {
                'testcase_id': testcase_id,
                'result_info': {
                    'run_result': testcase_result,
                    'is_solved': False,
                    'run_time': result['cpu_time'],
                    'memory': result['memory'],
                    'user_out': "",
                }
            }

            avg_run_time += result['cpu_time']
            avg_memory += result['memory']

            if -2 <= result['result'] <= -1: # Successful Run
                problem_is_solved = (problem_is_solved and result['is_solved'])
                submission_detail['result_info']['is_solved'] = result['is_solved']
                submission_detail['result_info']['user_out'] = result['output']
                if result['is_solved']:
                    passed_num += 1
            if final_result < result['result']:
                final_result = result['result']

            # DB -> Append values to the lists
            testcase_ids.append(testcase_id)
            submission_results.append(testcase_result)
            run_times.append(str(result['cpu_time']))
            memories.append(str(result['memory']))

            submission_detail_response.append(submission_detail)

        """
        Post-processing
        """
        if len(judge_result):
            avg_run_time //= len(judge_result)
            avg_memory //= len(judge_result)
        else:
            avg_run_time = 0
            avg_memory = 0

        testcase_ids = ','.join(testcase_ids)
        submission_results = ','.join(submission_results)
        run_times = ','.join(run_times)
        memories = ','.join(memories)

        """
        Create SubmissionDetail Record
        """
        SubmissionDetail.objects.create(
            submission_id=submission,
            testcase_id=testcase_ids,
            submission_result=submission_results,
            run_time=run_times,
            memory=memories
        )
        logger.debug(f"SubmissionDetail record created for submission ID: {submission_id}")

        """
        Update Submission Record
        """
        submission.passed_num = passed_num
        submission.total_num = total_num
        submission_result = SUBMISSION_RESULT.get(final_result, "")
        submission.avg_run_time = avg_run_time
        submission.avg_memory = avg_memory

        if submission_result:
            submission.final_result = submission_result
        else:
            logger.error(f"[Update Submission Record] Unexpected Submission result -> {final_result}")
            raise ValueError(f'[Update Submission Record] Unexpected Submission result -> {final_result}')
        
        submission.save()
        logger.info(f"Submission record updated with final results for submission ID: {submission_id}")
        
        submissions_a = Submission.objects.filter(problem_id=problem, user_id=user).order_by('-submitted_at')
        serializer = SubmissionSerializer(submissions_a, many=True, context={'exclude_submission_detail': True})
        
        if len(serializer.data) == 1:
            problem.attempt_number = F('attempt_number') + 1
        
        # Problem Solved
        if final_result == -2:
            solved_num = 0
            for i in serializer.data:
                if i['final_result'] == "SOLVED":
                    solved_num += 1
            if solved_num == 1:
                problem.solve_number = F('solve_number') + 1

        problem.save()
        logger.info(f"Problem record updated for problem ID: {problem.id}")

        """
        Compose response data with the code judgement execution result
        """
        response_data = {
            'submission_id': submission_id,
            'final_result': submission_result,
            'solution': user_code,
            'passed_num': passed_num,
            'total_num': total_num,
            'avg_run_time': avg_run_time,
            'avg_memory': avg_memory,
            'submission_detail': submission_detail_response,
            'submitted_at': submission.submitted_at,
        }

        logger.info(f"Submission response data composed successfully for submission ID: {submission_id}")
        return response_data

    except User.DoesNotExist:
        logger.error(f"User with ID {kwargs.get('user')} not found")
        raise ValueError(f"User with ID {kwargs.get('user')} not found")
    
    except Problem.DoesNotExist:
        logger.error(f"Problem with ID {kwargs.get('problem')} not found")
        raise ValueError(f"Problem with ID {kwargs.get('problem')} not found")

    except Language.DoesNotExist:
        logger.error(f"Language with ID {kwargs.get('language')} not found")
        raise ValueError(f"Language with ID {kwargs.get('language')} not found")

    except Exception as e:
        logger.error(f"Submission creation failed: {str(e)}", exc_info=True)
        raise ValueError(f"Submission creation failed: {str(e)}")