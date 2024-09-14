from django.conf import settings

RUN_BASE_DIR = settings.RUN_BASE_DIR
TESTCASE_BASE_DIR = settings.TESTCASE_BASE_DIR

default_env = ["LANG=en_US.UTF-8", "LANGUAGE=en_US:en", "LC_ALL=en_US.UTF-8"]
lang_config = {
    "c" : {
        "compile": {
            "src_name": "main.c",
            "solution_name" : "solution.c",
            "exe_name": "main",
            "max_cpu_time": 3000,
            "max_real_time": 5000,
            "max_memory": 128 * 1024 * 1024,
            "compile_command": "/usr/bin/gcc -O2 -w -fmax-errors=3 -std=c99 {src_path} -lm -o {exe_path}",
        },
        "run": {
            "command": "{exe_path}",
            "seccomp_rule": "c_cpp",
            "env": default_env
        }
    },
    "cpp" : {
        "compile": {
            "src_name": "main.cpp",
            "solution_name" : "solution.cpp",
            "exe_name": "main",
            "max_cpu_time": 3000,
            "max_real_time": 5000,
            "max_memory": 128 * 1024 * 1024,
            "compile_command": "/usr/bin/g++ -O2 -w -fmax-errors=3 -std=c++11 {src_path} -lm -o {exe_path}",
        },
        "run": {
            "command": "{exe_path}",
            "seccomp_rule": "c_cpp",
            "env": default_env
        }
    },
    "java" : {
        "compile": {
            "src_name": "Main.java",
            "solution_name" : "Solution.java",
            "exe_name": "Main",
            "max_cpu_time": 3000,
            "max_real_time": 5000,
            "max_memory": -1,
            "compile_command": "/usr/bin/javac {src_path} -d {exe_dir} -encoding UTF8"
        },
        "run": {
            "command": "/usr/bin/java -cp {exe_dir} -XX:MaxRAM={max_memory}k -Dfile.encoding=UTF-8 -Djava.security.policy==/etc/java_policy -Djava.awt.headless=true Main",
            "seccomp_rule": None,
            "env": ["LANG=en_US.UTF-8", "LANGUAGE=en_US:en", "LC_ALL=en_US.UTF-8"],
            "memory_limit_check_only": 1
        }
    },
    "js" : {
        "run": {
            "exe_name": "main.js",
            "solution_name" : "solution.js",
            "command": "/usr/bin/node {exe_path}",
            "seccomp_rule": None,
            "env": ["NO_COLOR=true"] + default_env,
            "memory_limit_check_only": 1
        }
    },
    "python" : {
        "compile": {
            "src_name": "main.py",
            "solution_name" : "solution.py",
            "exe_name": "main.py",
            "max_cpu_time": 3000,
            "max_real_time": 5000,
            "max_memory": 128 * 1024 * 1024,
            "compile_command": "/usr/bin/python3 -m py_compile {src_path}",
        },
        "run": {
            "command": "/usr/bin/python3 {exe_path}",
            "seccomp_rule": None,
            "env": ["PYTHONIOENCODING=UTF-8"] + default_env
        }
    }
}
