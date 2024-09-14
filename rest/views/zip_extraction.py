import os
import hashlib
import json
import zipfile

def extract_zip(zip_path, extract_to):
    """Extract a zip file to the specified directory and validate file pairs."""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        all_files = zip_ref.namelist()
        valid_files = []
        file_pairs = {}
        
        # Identify valid file pairs
        for file_name in all_files:
            if file_name.endswith('.in') or file_name.endswith('.out'):
                number_part = file_name.split('.')[0]
                try:
                    number = int(number_part)
                    if number not in file_pairs:
                        file_pairs[number] = {"in": False, "out": False}
                    if file_name.endswith('.in'):
                        file_pairs[number]["in"] = True
                    elif file_name.endswith('.out'):
                        file_pairs[number]["out"] = True
                except ValueError:
                    continue

        # Collect only valid pairs
        for number, pair in file_pairs.items():
            if pair["in"] and pair["out"]:
                valid_files.append(f"{number}.in")
                valid_files.append(f"{number}.out")

        # Extract only valid files
        for file_name in valid_files:
            zip_ref.extract(file_name, extract_to)

def calculate_md5(file_path, strip=False):
    """Calculate the MD5 checksum of a file, with an option to strip whitespace."""
    with open(file_path, 'rb') as f:
        file_content = f.read()
        if strip:
            file_content = file_content.strip()
        file_hash = hashlib.md5(file_content)
        return file_hash.hexdigest()

def collect_file_info(folder_path):
    """Collects information about file pairs in the given folder and returns it in a structured format."""
    files_info = {}
    file_pairs = {}
    max_number = 0

    # Scan through the folder and identify all .in and .out files
    for file_name in os.listdir(folder_path):
        if file_name.endswith('.in') or file_name.endswith('.out'):
            number_part = file_name.split('.')[0]
            try:
                number = int(number_part)
                max_number = max(max_number, number)
                if number not in file_pairs:
                    file_pairs[number] = {"in": False, "out": False}
                if file_name.endswith('.in'):
                    input_name = file_name
                    input_path = os.path.join(folder_path, file_name)
                    input_size = os.path.getsize(input_path)
                    input_md5 = calculate_md5(input_path)
                    file_pairs[number]["in"] = {
                        "input_name": input_name,
                        "input_size": input_size,
                        "input_md5": input_md5
                    }
                elif file_name.endswith('.out'):
                    output_name = file_name
                    output_path = os.path.join(folder_path, file_name)
                    output_size = os.path.getsize(output_path)
                    output_md5 = calculate_md5(output_path)
                    stripped_output_md5 = calculate_md5(output_path, strip=True)
                    file_pairs[number]["out"] = {
                        "output_name": output_name,
                        "output_size": output_size,
                        "output_md5": output_md5,
                        "stripped_output_md5": stripped_output_md5
                    }

                # Collect file information in the desired format
                if file_pairs[number]["in"] and file_pairs[number]["out"]:
                    files_info[str(number)] = {
                        "input_name": file_pairs[number]["in"]["input_name"],
                        "input_size": file_pairs[number]["in"]["input_size"],
                        "stripped_output_md5": file_pairs[number]["out"]["stripped_output_md5"],
                        "output_name": file_pairs[number]["out"]["output_name"],
                        "output_size": file_pairs[number]["out"]["output_size"],
                        "output_md5": file_pairs[number]["out"]["output_md5"]
                    }
            except ValueError:
                continue

    return {
        "testcase_number": len(files_info),
        "testcases": files_info
    }

def save_to_json(data, output_file):
    """Save the collected file information to a JSON file."""
    with open(output_file, 'w') as json_file:
        json.dump(data, json_file, indent=4)

"""
# Example usage
zip_path = 'test.zip'  # Replace with your zip file path
extract_to = './'  # Directory to extract files

try:
    # Extract the zip file
    extract_zip(zip_path, extract_to)
    # Collect file information from the extracted files
    data = collect_file_info(extract_to)
    # Save the collected information to a JSON file
    output_file = 'info.json'
    save_to_json(data, output_file)
    print("File information successfully saved to", output_file)
except ValueError as e:
    print(e)
"""