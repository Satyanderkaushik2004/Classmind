import os

files_to_check = ['main.py', 'sandbox.py']
print("Search for 'def run_code':")
for fn in files_to_check:
    if os.path.exists(fn):
        with open(fn, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if 'def run_code' in line:
                    print(f"{fn} Line {i+1}: {line.strip()}")
