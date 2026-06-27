import os

html_path = 'vyom_single.html'
if not os.path.exists(html_path):
    html_path = 'VYOM-main/vyom_single.html'

with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Verify the lines we want to replace
target_start = 15584 # 0-indexed is 15584
target_end = 15639 # 0-indexed is 15639

print("Target Start Line content:", repr(lines[target_start]))
print("Target End Line content:", repr(lines[target_end - 1]))

new_content = """  })), form.type === 'coding' && /*#__PURE__*/React.createElement(React.Fragment, null,
    /*#__PURE__*/React.createElement("div", {
      className: "form-group"
    }, /*#__PURE__*/React.createElement("label", null, "Programming Language"), /*#__PURE__*/React.createElement("select", {
      value: form.language || 'python',
      onChange: e => {
        const lang = e.target.value;
        setForm(f => ({
          ...f,
          language: lang,
          starter_code: f.starter_code ? f.starter_code : (
            lang === 'javascript' ? 'function solution() {\\n    // Your code here\\n}\\n\\nconsole.log(solution());' :
            lang === 'java' ? 'public class Main {\\n    public static void main(String[] args) {\\n        // Your code here\\n    }\\n}' :
            lang === 'cpp' ? '#include <iostream>\\nusing namespace std;\\n\\nint main() {\\n    // Your code here\\n    return 0;\\n}' :
            lang === 'c' ? '#include <stdio.h>\\n\\nint main() {\\n    // Your code here\\n    return 0;\\n}' :
            lang === 'go' ? 'package main\\n\\nimport "fmt"\\n\\nfunc main() {\\n    // Your code here\\n}' :
            'def solution():\\n    # Your code here\\n    pass\\n\\nprint(solution())'
          ),
          correct_answer: f.correct_answer ? f.correct_answer : (
            lang === 'javascript' ? 'function solution() {\\n    // Write reference solution here\\n    return 0;\\n}\\n\\nconsole.log(solution());' :
            lang === 'java' ? 'public class Main {\\n    public static int solution() {\\n        // Write reference solution here\\n        return 0;\\n    }\\n    public static void main(String[] args) {\\n        System.out.println(solution());\\n    }\\n}' :
            lang === 'cpp' ? '#include <iostream>\\nusing namespace std;\\n\\nint solution() {\\n    // Write reference solution here\\n    return 0;\\n}\\n\\nint main() {\\n    cout << solution() << endl;\\n    return 0;\\n}' :
            lang === 'c' ? '#include <stdio.h>\\n\\nint solution() {\\n    // Write reference solution here\\n    return 0;\\n}\\n\\nint main() {\\n    printf("%d\\\\n", solution());\\n    return 0;\\n}' :
            lang === 'go' ? 'package main\\n\\nimport "fmt"\\n\\nfunc solution() int {\\n    // Write reference solution here\\n    return 0\\n}\\n\\nfunc main() {\\n    fmt.Println(solution())\\n}' :
            'def solution():\\n    # Write reference solution here\\n    return 0\\n\\nprint(solution())'
          )
        }));
      },
      style: {
        width: '100%',
        padding: '8px 10px',
        borderRadius: 6,
        border: '1px solid var(--border)',
        background: 'var(--surface2)',
        color: 'var(--text)'
      }
    }, [
      {value: 'python', label: 'Python 3'},
      {value: 'javascript', label: 'JavaScript'},
      {value: 'java', label: 'Java'},
      {value: 'cpp', label: 'C++'},
      {value: 'c', label: 'C'},
      {value: 'go', label: 'Go'}
    ].map(opt => React.createElement("option", {key: opt.value, value: opt.value}, opt.label)))),
    /*#__PURE__*/React.createElement("div", {
      className: "form-group"
    }, /*#__PURE__*/React.createElement("label", null, "Starter Code ", /*#__PURE__*/React.createElement("span", {
      className: "text-muted text-xs"
    }, "(optional \\u2014 pre-filled in student editor)")), /*#__PURE__*/React.createElement("textarea", {
      rows: 4,
      value: form.starter_code || '',
      onChange: e => setForm(f => ({
        ...f,
        starter_code: e.target.value
      })),
      placeholder: form.language === 'javascript' ? '// JS starter code' : form.language === 'java' ? '// Java starter code' : form.language === 'cpp' ? '// C++ starter code' : form.language === 'go' ? '// Go starter code' : '# Python starter code',
      style: {
        fontFamily: "'Fira Code',Consolas,monospace",
        fontSize: '0.85rem',
        background: '#0d1117',
        color: '#c9d1d9'
      }
    })),
    /*#__PURE__*/React.createElement("div", {
      className: "form-group"
    }, /*#__PURE__*/React.createElement("label", null, "Reference Solution / Solution Code ", /*#__PURE__*/React.createElement("span", {
      className: "text-muted text-xs"
    }, "(required for output validation)")), /*#__PURE__*/React.createElement("textarea", {
      rows: 4,
      value: form.correct_answer || '',
      onChange: e => setForm(f => ({
        ...f,
        correct_answer: e.target.value
      })),
      placeholder: form.language === 'javascript' ? '// JS solved reference code' : form.language === 'java' ? '// Java solved reference code' : form.language === 'cpp' ? '// C++ solved reference code' : form.language === 'go' ? '// Go solved reference code' : '# Python solved reference code',
      style: {
        fontFamily: "'Fira Code',Consolas,monospace",
        fontSize: '0.85rem',
        background: '#0d1117',
        color: '#c9d1d9'
      }
    }))
"""

lines[target_start:target_end] = [new_content + '\n']

with open(html_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Replacement successful!")
