import re

def preprocess_code(student_code, correct_answer_code, starter_code, test_input):
    lang = "python"
    func_name = None
    func_match = re.search(r"def\s+(\w+)\s*\(", correct_answer_code)
    if not func_match:
        func_match = re.search(r"def\s+(\w+)\s*\(", starter_code)
    if func_match:
        func_name = func_match.group(1)
    
    global_calls = []
    for line in correct_answer_code.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and not line.startswith("\t"):
            if not (line.startswith("def ") or line.startswith("class ") or line.startswith("import ") or line.startswith("from ")):
                global_calls.append(line)
                
    if func_name:
        has_func_call = False
        for line in student_code.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("def "):
                continue
            if func_name in line:
                has_func_call = True
                break
        if not has_func_call and global_calls:
            student_code = student_code + "\n\n" + "\n".join(global_calls)
            
    if not test_input.strip() and func_name:
        pattern = rf"print\(\s*{func_name}\s*\((.*)\)\s*\)"
        match = re.search(pattern, correct_answer_code)
        if match:
            arg_str = match.group(1).strip()
            if arg_str.startswith("{") or arg_str.startswith("[") or arg_str.startswith("'") or arg_str.startswith('"'):
                test_input = arg_str
                
    return student_code, test_input

# TEST CASES
correct_answer_code = """def count_vertices(graph):
    return len(graph)

# Sample call
print(count_vertices({'A': ['B', 'C'], 'B': ['C'], 'C': [], 'D': ['A']}))"""

starter_code = """def count_vertices(graph):
    return len(graph)

# Sample call
print(count_vertices({'A': ['B', 'C'], 'B': ['C'], 'C': [], 'D': ['A']}))"""

# Test 1: Student uses eval(input()) approach
student_code_1 = """def count_vertices(graph):
    return len(graph)

# Input
graph = eval(input())

# Output
print(count_vertices(graph))"""

sc1, ti1 = preprocess_code(student_code_1, correct_answer_code, starter_code, "")
print("TEST 1 (eval(input())):")
print("Modified Student Code:\n", sc1)
print("Modified Test Input:\n", ti1)
print("-" * 50)

# Test 2: Student uses only the function definition (different approach)
student_code_2 = """def count_vertices(graph):
    vertices = set(graph.keys())
    for neighbors in graph.values():
        vertices.update(neighbors)
    return len(vertices)"""

sc2, ti2 = preprocess_code(student_code_2, correct_answer_code, starter_code, "")
print("TEST 2 (only function):")
print("Modified Student Code:\n", sc2)
print("Modified Test Input:\n", ti2)
print("-" * 50)
