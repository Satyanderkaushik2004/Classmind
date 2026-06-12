filepath = r"c:\Users\robin\Downloads\Classmind-main (1)\Classmind-main\vyom_single.html"

with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if "🧠" in line or "\\uD83E\\uDDE0" in line:
        if "React.createElement" in line or "className" in line or "<div" in line or "<span" in line:
            # Safely print without unicode characters using ascii replacement
            safe_line = line.strip()[:150].encode("ascii", "replace").decode("ascii")
            print(f"Line {idx+1}: {safe_line}")
