import sys
sys.path.append(".")
from sandbox import run_code

# Test 1: Java with Class 'Solution' and 'package' declaration
java_code = """
package com.vyom.student;

class Helper {
    public static void greet() {
        System.out.println("Greetings from Helper!");
    }
}

public class Solution {
    public static void main(String[] args) {
        System.out.println("Hello from Custom Solution class!");
        Helper.greet();
    }
}
"""
print("--- Running Test 1: Java Custom Class & Package ---")
res_java = run_code(java_code, "java")
print("Java Output:")
print(res_java.output)
print("Java Error status:", res_java.error)
print("Java Timed Out status:", res_java.timed_out)
assert res_java.error is False, "Java test failed!"
print("Test 1 Passed!\n")


# Test 2: Go code build and execution
go_code = """
package main

import (
    "fmt"
    "time"
)

func main() {
    start := time.Now()
    fmt.Println("Hello from compiled Go sandbox!")
    fmt.Printf("Execution completed successfully in %v\\n", time.Since(start))
}
"""
print("--- Running Test 2: Go Build Execution ---")
res_go = run_code(go_code, "go")
print("Go Output:")
print(res_go.output)
print("Go Error status:", res_go.error)
print("Go Timed Out status:", res_go.timed_out)
assert res_go.error is False, "Go test failed!"
print("Test 2 Passed!\n")

print("All tests passed successfully!")
