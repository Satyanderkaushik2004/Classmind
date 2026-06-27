import re

filepath = r"c:\Users\robin\Downloads\Classmind-main (1)\Classmind-main\vyom_single.html"

selectors = [
    r"\.teacher-sidebar", r"\.sidebar-nav", r"\.sidebar-logo-icon", r"\.nav-brand",
    r"\.card", r"\.btn", r"\.btn-primary", r"\.landing-hero"
]

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for sel in selectors:
    pattern = re.compile(sel)
    print(f"=== Matches for {sel} ===")
    matches = 0
    for idx, line in enumerate(lines):
        if pattern.search(line):
            print(f"  Line {idx+1}: {line.strip()[:100]}")
            matches += 1
            if matches >= 5:
                print("  ... (more matches)")
                break
