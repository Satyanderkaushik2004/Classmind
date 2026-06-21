import os

html_path = 'vyom_single.html'
if not os.path.exists(html_path):
    html_path = 'VYOM-main/vyom_single.html'

with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 1. Update templatesByLang and generateCodingQuestion
# Search for lines containing const templatesByLang = { and topic = ''; }
start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if 'const templatesByLang =' in line:
        start_idx = i
    if start_idx is not None and "setTopic('');" in line:
        # Find the next closing brace
        for j in range(i, len(lines)):
            if lines[j].strip() == '}':
                end_idx = j + 1
                break
        break

print(f"Found templatesByLang block from line {start_idx + 1} to {end_idx}")
if start_idx is None or end_idx is None:
    raise ValueError("Could not find templatesByLang block!")

new_templates_and_generator = """  const templatesByLang = {
    python: [
      {
        question: `Write a Python function \`sum_list(nums)\` that takes a list of integers and returns their sum.\\n\\n**Input Format:** A list of integers, e.g. [1, 2, 3]\\n**Output Format:** A single integer\\n**Constraints:** 1 ≤ len(nums) ≤ 1000, each element in [-10^4, 10^4]\\n\\n**Sample Test Case:**\\nInput: [1, 2, 3, 4, 5]\\nExpected Output: 15`,
        starter_code: `def sum_list(nums):\\n    # Your code here\\n    pass\\n\\nprint(sum_list([1, 2, 3, 4, 5]))`,
        reference_solution: `def sum_list(nums):\\n    return sum(nums)\\n\\nprint(sum_list([1, 2, 3, 4, 5]))`
      },
      {
        question: `Write a Python function \`count_vowels(s)\` that returns the number of vowels (a, e, i, o, u) in a string (case-insensitive).\\n\\n**Input Format:** A string s\\n**Output Format:** An integer count\\n**Constraints:** 1 ≤ len(s) ≤ 500\\n\\n**Sample Test Case:**\\nInput: "Hello World"\\nExpected Output: 3`,
        starter_code: `def count_vowels(s):\\n    # Your code here\\n    pass\\n\\nprint(count_vowels("Hello World"))`,
        reference_solution: `def count_vowels(s):\\n    return sum(1 for char in s.lower() if char in 'aeiou')\\n\\nprint(count_vowels("Hello World"))`
      }
    ],
    javascript: [
      {
        question: `Write a JavaScript function \`sumList(nums)\` that takes an array of integers and returns their sum.\\n\\n**Input Format:** An array of integers, e.g. [1, 2, 3]\\n**Output Format:** A single integer\\n**Constraints:** 1 ≤ nums.length ≤ 1000\\n\\n**Sample Test Case:**\\nInput: [1, 2, 3, 4, 5]\\nExpected Output: 15`,
        starter_code: `function sumList(nums) {\\n    // Your code here\\n}\\n\\nconsole.log(sumList([1, 2, 3, 4, 5]));`,
        reference_solution: `function sumList(nums) {\\n    return nums.reduce((a, b) => a + b, 0);\\n}\\n\\nconsole.log(sumList([1, 2, 3, 4, 5]));`
      },
      {
        question: `Write a JavaScript function \`countVowels(s)\` that returns the number of vowels (a, e, i, o, u) in a string (case-insensitive).\\n\\n**Input Format:** A string s\\n**Output Format:** An integer count\\n**Constraints:** 1 ≤ s.length ≤ 500\\n\\n**Sample Test Case:**\\nInput: "Hello World"\\nExpected Output: 3`,
        starter_code: `function countVowels(s) {\\n    // Your code here\\n}\\n\\nconsole.log(countVowels("Hello World"));`,
        reference_solution: `function countVowels(s) {\\n    let count = 0;\\n    for (let char of s.toLowerCase()) {\\n        if ('aeiou'.includes(char)) count++;\\n    }\\n    return count;\\n}\\n\\nconsole.log(countVowels("Hello World"));`
      }
    ],
    java: [
      {
        question: `Write a Java method \`sumList(int[] nums)\` inside class Main that takes an array of integers and returns their sum.\\n\\n**Input Format:** An array of integers, e.g. {1, 2, 3}\\n**Output Format:** A single integer\\n\\n**Sample Test Case:**\\nInput: {1, 2, 3, 4, 5}\\nExpected Output: 15`,
        starter_code: `public class Main {\\n    public static int sumList(int[] nums) {\\n        // Your code here\\n        return 0;\\n    }\\n    public static void main(String[] args) {\\n        System.out.println(sumList(new int[]{1, 2, 3, 4, 5}));\\n    }\\n}`,
        reference_solution: `public class Main {\\n    public static int sumList(int[] nums) {\\n        int sum = 0;\\n        for (int n : nums) sum += n;\\n        return sum;\\n    }\\n    public static void main(String[] args) {\\n        System.out.println(sumList(new int[]{1, 2, 3, 4, 5}));\\n    }\\n}`
      },
      {
        question: `Write a Java method \`countVowels(String s)\` inside class Main that returns the number of vowels (a, e, i, o, u) in a string (case-insensitive).\\n\\n**Input Format:** A String s\\n**Output Format:** An integer count\\n\\n**Sample Test Case:**\\nInput: "Hello World"\\nExpected Output: 3`,
        starter_code: `public class Main {\\n    public static int countVowels(String s) {\\n        // Your code here\\n        return 0;\\n    }\\n    public static void main(String[] args) {\\n        System.out.println(countVowels("Hello World"));\\n    }\\n}`,
        reference_solution: `public class Main {\\n    public static int countVowels(String s) {\\n        int count = 0;\\n        for (char c : s.toLowerCase().toCharArray()) {\\n            if ("aeiou".indexOf(c) != -1) count++;\\n        }\\n        return count;\\n    }\\n    public static void main(String[] args) {\\n        System.out.println(countVowels("Hello World"));\\n    }\\n}`
      }
    ],
    cpp: [
      {
        question: `Write a C++ function \`sumList(vector<int>& nums)\` that takes a vector of integers and returns their sum.\\n\\n**Input Format:** A vector of integers, e.g. {1, 2, 3}\\n**Output Format:** A single integer\\n\\n**Sample Test Case:**\\nInput: {1, 2, 3, 4, 5}\\nExpected Output: 15`,
        starter_code: `#include <iostream>\\n#include <vector>\\nusing namespace std;\\n\\nint sumList(vector<int>& nums) {\\n    // Your code here\\n    return 0;\\n}\\n\\nint main() {\\n    vector<int> nums = {1, 2, 3, 4, 5};\\n    cout << sumList(nums) << endl;\\n    return 0;\\n}`,
        reference_solution: `#include <iostream>\\n#include <vector>\\nusing namespace std;\\n\\nint sumList(vector<int>& nums) {\\n    int sum = 0;\\n    for (int n : nums) sum += n;\\n    return sum;\\n}\\n\\nint main() {\\n    vector<int> nums = {1, 2, 3, 4, 5};\\n    cout << sumList(nums) << endl;\\n    return 0;\\n}`
      },
      {
        question: `Write a C++ function \`countVowels(string s)\` that returns the number of vowels (a, e, i, o, u) in a string (case-insensitive).\\n\\n**Input Format:** A string s\\n**Output Format:** An integer count\\n\\n**Sample Test Case:**\\nInput: "Hello World"\\nExpected Output: 3`,
        starter_code: `#include <iostream>\\n#include <string>\\nusing namespace std;\\n\\nint countVowels(string s) {\\n    // Your code here\\n    return 0;\\n}\\n\\nint main() {\\n    cout << countVowels("Hello World") << endl;\\n    return 0;\\n}`,
        reference_solution: `#include <iostream>\\n#include <string>\\nusing namespace std;\\n\\nint countVowels(string s) {\\n    int count = 0;\\n    string vowels = "aeiouAEIOU";\\n    for (char c : s) {\\n        if (vowels.find(c) != string::npos) count++;\\n    }\\n    return count;\\n}\\n\\nint main() {\\n    cout << countVowels("Hello World") << endl;\\n    return 0;\\n}`
      }
    ],
    c: [
      {
        question: `Write a C function \`sum_array(int arr[], int size)\` that takes an array of integers and its size, and returns their sum.\\n\\n**Input Format:** An array of integers and its size\\n**Output Format:** A single integer\\n\\n**Sample Test Case:**\\nInput: {1, 2, 3, 4, 5}, 5\\nExpected Output: 15`,
        starter_code: `#include <stdio.h>\\n\\nint sum_array(int arr[], int size) {\\n    // Your code here\\n    return 0;\\n}\\n\\nint main() {\\n    int arr[] = {1, 2, 3, 4, 5};\\n    printf("%d\\\\n", sum_array(arr, 5));\\n    return 0;\\n}`,
        reference_solution: `#include <stdio.h>\\n\\nint sum_array(int arr[], int size) {\\n    int sum = 0;\\n    for (int i = 0; i < size; i++) sum += arr[i];\\n    return sum;\\n}\\n\\nint main() {\\n    int arr[] = {1, 2, 3, 4, 5};\\n    printf("%d\\\\n", sum_array(arr, 5));\\n    return 0;\\n}`
      },
      {
        question: `Write a C function \`count_vowels(const char* s)\` that returns the number of vowels (a, e, i, o, u) in a string (case-insensitive).\\n\\n**Input Format:** A string s\\n**Output Format:** An integer count\\n\\n**Sample Test Case:**\\nInput: "Hello World"\\nExpected Output: 3`,
        starter_code: `#include <stdio.h>\\n\\nint count_vowels(const char* s) {\\n    // Your code here\\n    return 0;\\n}\\n\\nint main() {\\n    printf("%d\\\\n", count_vowels("Hello World"));\\n    return 0;\\n}`,
        reference_solution: `#include <stdio.h>\\n#include <ctype.h>\\n\\nint count_vowels(const char* s) {\\n    int count = 0;\\n    while (*s) {\\n        char c = tolower(*s);\\n        if (c == \'a\' || c == \'e\' || c == \'i\' || c == \'o\' || c == \'u\') count++;\\n        s++;\\n    }\\n    return count;\\n}\\n\\nint main() {\\n    printf("%d\\\\n", count_vowels("Hello World"));\\n    return 0;\\n}`
      }
    ],
    go: [
      {
        question: `Write a Go function \`sumSlice(nums []int) int\` that takes a slice of integers and returns their sum.\\n\\n**Input Format:** A slice of integers, e.g. []int{1, 2, 3}\\n**Output Format:** A single integer\\n\\n**Sample Test Case:**\\nInput: []int{1, 2, 3, 4, 5}\\nExpected Output: 15`,
        starter_code: `package main\\n\\nimport "fmt"\\n\\nfunc sumSlice(nums []int) int {\\n    // Your code here\\n    return 0\\n}\\n\\nfunc main() {\\n    fmt.Println(sumSlice([]int{1, 2, 3, 4, 5}))\\n}`,
        reference_solution: `package main\\n\\nimport "fmt"\\n\\nfunc sumSlice(nums []int) int {\\n    sum := 0\\n    for _, n := range nums {\\n        sum += n\\n    }\\n    return sum\\n}\\n\\nfunc main() {\\n    fmt.Println(sumSlice([]int{1, 2, 3, 4, 5}))\\n}`
      },
      {
        question: `Write a Go function \`countVowels(s string) int\` that returns the number of vowels (a, e, i, o, u) in a string (case-insensitive).\\n\\n**Input Format:** A string s\\n**Output Format:** An integer count\\n\\n**Sample Test Case:**\\nInput: "Hello World"\\nExpected Output: 3`,
        starter_code: `package main\\n\\nimport "fmt"\\n\\nfunc countVowels(s string) int {\\n    // Your code here\\n    return 0\\n}\\n\\nfunc main() {\\n    fmt.Println(countVowels("Hello World"))\\n}`,
        reference_solution: `package main\\n\\nimport "fmt"\\nimport "strings"\\n\\nfunc countVowels(s string) int {\\n    count := 0\\n    vowels := "aeiouAEIOU"\\n    for _, char := range s {\\n        if strings.ContainsRune(vowels, char) {\\n            count++\\n        }\\n    }\\n    return count\\n}\\n\\nfunc main() {\\n    fmt.Println(countVowels("Hello World"))\\n}`
      }
    ]
  };

  async function generateCodingQuestion() {
    setLoading(true);
    const apiKey = localStorage.getItem('cm_gemini_key') || '';
    const langKey = (language || 'python').toLowerCase();
    const langLabel = langKey === 'cpp' ? 'C++' : langKey.charAt(0).toUpperCase() + langKey.slice(1);
    
    try {
      if (apiKey && topic.trim()) {
        const prompt = `Generate a beginner-level ${langLabel} coding question about "${topic}".\\nReturn ONLY a JSON object with exactly these fields:\\n{\\n  "question": "Full problem statement in ${langLabel} including Input Format, Output Format, Constraints, and one Sample Test Case",\\n  "starter_code": "${langLabel} starter code with a function stub / main method and a sample call/print statement",\\n  "reference_solution": "Full correct working code that solves the question and prints the expected output for the sample case"\\n}\\nNo markdown fences, no explanation. Raw JSON only.`;
        const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${apiKey}`,
            "HTTP-Referer": window.location.origin,
            "X-Title": "VYOM AI"
          },
          body: JSON.stringify({
            model: "openai/gpt-4o-mini",
            messages: [{
              role: "user",
              content: prompt
            }]
          })
        });
        const data = await res.json();
        const text = data?.choices?.[0]?.message?.content || '{}';
        const clean = text.replace(/```json|```/g, '').trim();
        const parsed = JSON.parse(clean);
        onGenerated({
          question: parsed.question,
          starter_code: parsed.starter_code,
          reference_solution: parsed.reference_solution || parsed.starter_code
        });
        add(`⚡ ${langLabel} coding question generated!`, 'success');
      } else {
        // fallback: pick a random template for this language
        await new Promise(r => setTimeout(r, 600));
        const templates = templatesByLang[langKey] || templatesByLang['python'];
        const t = templates[Math.floor(Math.random() * templates.length)];
        onGenerated(t);
        if (!apiKey) add('Using template — add an AI key for custom generation', 'info');else add(`⚡ ${langLabel} coding question generated!`, 'success');
      }
    } catch (e) {
      // fallback on error
      const templates = templatesByLang[langKey] || templatesByLang['python'];
      const t = templates[Math.floor(Math.random() * templates.length)];
      onGenerated(t);
      add('⚡ Sample coding question loaded', 'info');
    }
    setLoading(false);
    setShowInput(false);
    setTopic('');
  }
"""

lines[start_idx:end_idx] = [new_templates_and_generator]

# 2. Update StudentTestCodeEditor usage value prop around line 21850 (we need to find it dynamically)
editor_usage_idx = None
for i, line in enumerate(lines):
    if 'StudentTestCodeEditor' in line:
        # Search next few lines for value:
        for j in range(i, i+10):
            if 'value:' in lines[j] and 'task.correct_answer' in lines[j]:
                editor_usage_idx = j
                break
        if editor_usage_idx:
            break

print(f"Found StudentTestCodeEditor usage at line {editor_usage_idx + 1}")
if editor_usage_idx:
    lines[editor_usage_idx] = "          value: testAnswers[task.id] !== undefined ? testAnswers[task.id] : (task.starter_code || task.correct_answer || ''),\n"
else:
    raise ValueError("Could not find StudentTestCodeEditor value prop!")

# 3. Update StudentCodeEditor initialization code around line 23517
editor_init_idx = None
for i, line in enumerate(lines):
    if 'function StudentCodeEditor(' in line:
        for j in range(i, i+10):
            if 'task.correct_answer' in lines[j]:
                editor_init_idx = j
                break
        if editor_init_idx:
            break

print(f"Found StudentCodeEditor initialization at line {editor_init_idx + 1}")
if editor_init_idx:
    lines[editor_init_idx] = "    try { return localStorage.getItem(`cm_code_${sessionCode}_${task.id}`) || task.starter_code || task.correct_answer || ''; } catch { return task.starter_code || task.correct_answer || ''; }\n"
else:
    raise ValueError("Could not find StudentCodeEditor state initialization!")

with open(html_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("All replacements done successfully!")
