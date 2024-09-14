import hashlib

def generate_problem_list_cache_key(user_id):
    return f"problem_list_user_{user_id}" if user_id else "problem_list_anonymous"

def generate_problem_cache_key(problem_id):
    return f"problem_{problem_id}"

def generate_problem_meta_cache_key(problem_id):
    return f"problem_meta_{problem_id}"

def generate_submission_cache_key(user_id, problem_id, language_id, user_code):
    # Use a hash of the user code to generate a unique cache key
    code_hash = hashlib.sha256(user_code.encode('utf-8')).hexdigest()
    return f"user_{user_id}_problem_{problem_id}_language_{language_id}_code_{code_hash}"