import os

html_path = 'vyom_single.html'
if not os.path.exists(html_path):
    html_path = 'VYOM-main/vyom_single.html'

with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if "form.type === 'coding' && /*#__PURE__*/React.createElement(AICodingGenerator" in line:
        start_idx = i
        # Find ending match of AICodingGenerator
        for j in range(i, len(lines)):
            if '}))' in lines[j] and 'React.createElement("textarea"' in lines[j]:
                end_idx = j + 1
                break
        break

print(f"Found AICodingGenerator mount from line {start_idx + 1} to {end_idx}")
if start_idx is None or end_idx is None:
    raise ValueError("Could not find AICodingGenerator mount!")

# We want to replace everything from start_idx up to the textarea tag.
# Let's inspect the target lines to make sure we keep the textarea tag intact.
target_line = lines[end_idx - 1]
print("Target line with textarea:", repr(target_line))

# We want to split the target line at the textarea tag start.
split_parts = target_line.split('/*#__PURE__*/React.createElement("textarea"')
textarea_part = '/*#__PURE__*/React.createElement("textarea"' + split_parts[1]

new_mount = """  }, "*")), form.type === 'coding' && /*#__PURE__*/React.createElement(AICodingGenerator, {
    language: form.language || 'python',
    setLanguage: lang => setForm(f => ({
      ...f,
      language: lang,
      starter_code: lang === 'javascript' ? 'function solution() {\\n    // Your code here\\n}\\n\\nconsole.log(solution());' :
            lang === 'java' ? 'public class Main {\\n    public static void main(String[] args) {\\n        // Your code here\\n    }\\n}' :
            lang === 'cpp' ? '#include <iostream>\\nusing namespace std;\\n\\nint main() {\\n    // Your code here\\n    return 0;\\n}' :
            lang === 'c' ? '#include <stdio.h>\\n\\nint main() {\\n    // Your code here\\n    return 0;\\n}' :
            lang === 'go' ? 'package main\\n\\nimport "fmt"\\n\\nfunc main() {\\n    // Your code here\\n}' :
            'def solution():\\n    # Your code here\\n    pass\\n\\nprint(solution())',
      correct_answer: lang === 'javascript' ? 'function solution() {\\n    // Write reference solution here\\n    return 0;\\n}\\n\\nconsole.log(solution());' :
            lang === 'java' ? 'public class Main {\\n    public static int solution() {\\n        // Write reference solution here\\n        return 0;\\n    }\\n    public static void main(String[] args) {\\n        System.out.println(solution());\\n    }\\n}' :
            lang === 'cpp' ? '#include <iostream>\\nusing namespace std;\\n\\nint solution() {\\n    // Write reference solution here\\n    return 0;\\n}\\n\\nint main() {\\n    cout << solution() << endl;\\n    return 0;\\n}' :
            lang === 'c' ? '#include <stdio.h>\\n\\nint solution() {\\n    // Write reference solution here\\n    return 0;\\n}\\n\\nint main() {\\n    printf("%d\\\\n", solution());\\n    return 0;\\n}' :
            lang === 'go' ? 'package main\\n\\nimport "fmt"\\n\\nfunc solution() int {\\n    // Write reference solution here\\n    return 0\\n}\\n\\nfunc main() {\\n    fmt.Println(solution())\\n}' :
            'def solution():\\n    # Write reference solution here\\n    return 0\\n\\nprint(solution())'
    })),
    onGenerated: q => {
      setForm(f => ({
        ...f,
        question: q.question,
        starter_code: q.starter_code || f.starter_code,
        correct_answer: q.reference_solution || f.correct_answer
      }));
    }
  })), """ + textarea_part

lines[start_idx:end_idx] = [new_mount]

with open(html_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Mount updated successfully!")
