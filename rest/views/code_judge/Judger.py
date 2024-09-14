import Cjudger
import uuid
import os
import shutil
import shlex
import psutil
import json
import hashlib
from multiprocessing import Pool
from .config import TESTCASE_BASE_DIR

class SubmissionDriver:
    def __init__(self, base_workspace, testcase_name):
        self.submission_id = uuid.uuid4().hex
        self.work_dir = os.path.join(base_workspace, self.submission_id)
        test_dir = os.path.join(TESTCASE_BASE_DIR, testcase_name)
        if os.path.exists(test_dir):
            self.test_dir = test_dir
        else:
            self.test_dir = None
        pass

    def __enter__(self):
        try:
            os.mkdir(self.work_dir)
            #os.chown(self.work_dir, COMPILER_UID, RUN_GID) #유저 보안 설정 추후
            #os.chmod(self.work_dir, 0o711)
        except Exception as e:
            pass #error
        return self.work_dir, self.test_dir

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            shutil.rmtree(self.work_dir)
            pass
        except Exception as e:
            pass #error

class Compiler:
    def compile(self, compile_config, src_path, output_dir):
        compile_command = compile_config["compile_command"]
        exe_path = os.path.join(output_dir, compile_config["exe_name"])
        
        compiler_out = os.path.join(output_dir, "compiler.out") #컴파일 결과

        compile_command = compile_command.format(src_path=src_path, exe_dir=output_dir, exe_path=exe_path)
        command = shlex.split(compile_command)

        env = compile_config.get("env", []) #환경변수 지정
        env.append("PATH=" + os.getenv("PATH"))

        os.chdir(output_dir)

        result = Cjudger.run(max_cpu_time=compile_config["max_cpu_time"],
                             max_real_time=compile_config["max_real_time"],
                             max_memory=compile_config["max_memory"],
                             max_stack=128 * 1024 * 1024,
                             max_output_size=20 * 1024 * 1024,
                             max_process_number=-1,
                             exe_path=command[0],
                             input_path="/dev/null",
                             output_path=compiler_out,
                             error_path=compiler_out,
                             args=command[1::],
                             env=env,
                             seccomp_rule_name=None,
                             uid=0,
                             gid=0)
                             #uid gid는 추후 수정해야함
        error_msg = ""
        # 컴파일 에러 발생

        if result["result"] != Cjudger.RESULT_SUCCESS:
            if os.path.exists(compiler_out):
                with open(compiler_out, encoding="utf-8") as f:
                    error_msg = f.read().strip()
                    #os.remove(compiler_out)
                    return "", error_msg
        else:
            #os.remove(compiler_out)
            return exe_path, error_msg

class Judger:
    def __init__(self, run_config, exe_path, max_cpu_time, max_real_time, max_memory, testcase_dir, submission_dir):
        self.run_config = run_config
        self.exe_path = exe_path

        self.max_cpu_time = max_cpu_time
        self.max_real_time = max_real_time
        self.max_memory = max_memory
        
        self.testcase_dir = testcase_dir
        self.submission_dir = submission_dir

        self.pool = Pool(processes=psutil.cpu_count())
        self.testcase_info = self.load_test_info()
    
    def load_test_info(self):
        try:
            with open(os.path.join(self.testcase_dir, "info.json")) as f:
                return json.load(f)
        except IOError:
            raise Exception("Test case info not found")
        except ValueError:
            raise Exception("Wrong test case config")

    def judge_one(self, testcase_id): #테스트케이스 하나 채점
        testcase_info = self.testcase_info["testcases"][testcase_id]
        input_path = os.path.join(self.testcase_dir, testcase_info["input_name"])

        user_output_path = os.path.join(self.submission_dir, testcase_id + ".out")
        error_msg_path = os.path.join(self.submission_dir, "compiler.out")

        command = self.run_config["command"].format(exe_path=self.exe_path, exe_dir=os.path.dirname(self.exe_path),max_memory=int(self.max_memory / 1024)) #max_memory를 1024로 나누는 이유는 java의 경우 kb단위이기 때문
        command = shlex.split(command)
        env = ["PATH=" + os.environ.get("PATH", "")] + self.run_config.get("env", [])

        seccomp_rule = self.run_config["seccomp_rule"]
        run_result = Cjudger.run(max_cpu_time=self.max_cpu_time,
                                 max_real_time=self.max_real_time,
                                 max_memory=self.max_memory,
                                 max_stack=128 * 1024 * 1024,
                                 max_output_size=max(testcase_info.get("output_size", 0) * 2, 1024 * 1024 * 16),
                                 max_process_number=Cjudger.UNLIMITED,
                                 input_path = input_path,
                                 output_path = user_output_path,
                                 error_path = error_msg_path,
                                 exe_path=command[0],
                                 args=command[1::],
                                 env=env,
                                 seccomp_rule_name=seccomp_rule,
                                 memory_limit_check_only=self.run_config.get("memory_limit_check_only", 0),
                                 uid=0,
                                 gid=0
                                 )
                                 #uid gid는 나중에
        run_result["testcase"] = testcase_id

        run_result["output_md5"] = None
        run_result["output"] = None
        run_result["stdout"] = ""
        if run_result["result"] == Cjudger.RESULT_SUCCESS:
            if not os.path.exists(user_output_path):
                run_result["result"] = Cjudger.RESULT_WRONG_ANSWER
            else:
                #정답 체크
                with open(user_output_path, "rb") as f:
                    content = f.read()

                content_str = content.decode('utf-8', errors='backslashreplace')
                return_index = content_str.find("[!return]:")

                if return_index != -1:
                    content_relevant = content_str[return_index + len("[!return]:"):].rstrip()
                else:
                    content_relevant = ""
                
                run_result["stdout"] = content_str[:return_index]
                
                output_md5 = hashlib.md5(content_relevant.encode('utf-8')).hexdigest()
                run_result["output"] = content_relevant.strip()
                result = (output_md5 == self.testcase_info["testcases"][testcase_id]["stripped_output_md5"])

                run_result["output_md5"], is_solved, run_result['is_solved'] = output_md5, result, result

                if not is_solved:
                    run_result["result"] = Cjudger.RESULT_WRONG_ANSWER

                return run_result
        elif run_result["result"] in [Cjudger.RESULT_CPU_TIME_LIMIT_EXCEEDED, Cjudger.RESULT_REAL_TIME_LIMIT_EXCEEDED]:
            pass
        elif run_result["result"] == Cjudger.RESULT_RUNTIME_ERROR:
            pass
        else:
            pass

        """ compiler error message for {js, python} is stored """
        try:
            with open(error_msg_path, "rb") as f:
                run_result["output"] = f.read().decode("utf-8", errors="backslashreplace")
        except Exception:
            pass
        #print(f"Error Run Result : {run_result}")
        return run_result

    def run(self, batch_size=6):  # batch_size로 테스트 케이스를 나누어 채점
        result = []

        #tmp_result = []
        #for testcase_id, _ in self.testcase_info["testcases"].items():
        #    tmp_result.append(self.judge_one(testcase_id))
        #    print("suc")
            
        #for item in tmp_result:
        #    result.append(item.get())
        #return result
        # Get all test cases as a list
        testcases = list(self.testcase_info["testcases"].items())


        # Process in batches
        for i in range(0, len(testcases), batch_size):
            batch = testcases[i:i + batch_size]
            tmp_result = []

            with Pool(processes=psutil.cpu_count()) as pool:
                for testcase_id, _ in batch:
                    tmp_result.append(pool.apply_async(_run, (self, testcase_id)))

                pool.close()
                pool.join()

                for item in tmp_result:
                    result.append(item.get())

        return result

    def __getstate__(self):
        self_dict = self.__dict__.copy()
        del self_dict["pool"]
        return self_dict

def _run(instance, testcase_id):
    return instance.judge_one(testcase_id)