import os
import re
import json
import requests
import openai

# --- Config ---
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["GITHUB_REPO"]
PR_NUMBER = os.environ["PR_NUMBER"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

GITHUB_API = f"https://api.github.com/repos/{REPO}"

# --- Helpers ---
def get_pr_files():
    url = f"{GITHUB_API}/pulls/{PR_NUMBER}/files"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def parse_patch_to_line_map(patch):
    """
    Parses a unified diff patch and returns mapping:
    diff_line_number -> absolute_file_line_number
    """
    line_map = {}
    if not patch:
        return line_map

    file_line = None
    diff_line = 0

    for line in patch.splitlines():
        diff_line += 1
        if line.startswith("@@"):
            # Example: @@ -21,7 +21,9 @@
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            if m:
                file_line = int(m.group(1)) - 1
        elif line.startswith("+"):
            file_line += 1
            line_map[diff_line] = file_line
        elif line.startswith("-"):
            continue
        else:
            file_line += 1
    return line_map

def analyze_code_with_ai(filename, patch):
    """
    Ask AI to generate review comments with severity.
    Must return JSON list: 
    [
      {"diff_line": <diff_line>, "severity": "Critical|Warning|Suggestion", "comment": "<text>"}
    ]
    """
    openai.api_key = OPENAI_API_KEY

    prompt = f"""
    You are a python code reviewer.
     Review the following Pull Request diff for `{filename}`
    - Point out syntax errors if any
    - Suggest cleaner or more efficient alternatives
    - Give feedback in concise bullet points

    For each finding:
    - Use `severity` field with one of: Critical, Warning, Suggestion
    - Critical = bugs, security, crashes
    - Warning = performance, readability, maintainability issues
    - Suggestion = stylistic improvements, best practices

    Return STRICT JSON array only, like:
    [
      {{"diff_line": 42, "severity": "Critical", "comment": "Null reference risk here."}},
      {{"diff_line": 55, "severity": "Suggestion", "comment": "Consider using 'using' statement for disposal."}}
    ]

    Diff:
    {patch}
    """

    resp = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0,
    )
    text = resp.choices[0].message["content"].strip()
    try:
        return json.loads(text)
    except Exception:
        return []

def decorate_comment(severity, comment):
    if severity.lower() == "critical":
        return f"⚠️ **Critical**: {comment}"
    elif severity.lower() == "warning":
        return f"⚡ **Warning**: {comment}"
    else:
        return f"💡 **Suggestion**: {comment}"

def post_review(comments):
    url = f"{GITHUB_API}/pulls/{PR_NUMBER}/reviews"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "body": "🤖 Automated AI code review suggestions",
        "event": "COMMENT",
        "comments": comments,
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

def main():
    files = get_pr_files()
    review_comments = []

    for file in files:
        if not file["filename"].endswith(".cs"):
            continue
        patch = file.get("patch")
        if not patch:
            continue

        diff_map = parse_patch_to_line_map(patch)
        suggestions = analyze_code_with_ai(file["filename"], patch)

        for s in suggestions:
            diff_line = s.get("diff_line")
            abs_line = diff_map.get(diff_line)
            if abs_line:
                review_comments.append({
                    "path": file["filename"],
                    "line": abs_line,
                    "side": "RIGHT",
                    "body": decorate_comment(s.get("severity", "Suggestion"), s.get("comment")),
                })

    if review_comments:
        post_review(review_comments)
    else:
        post_review([{
            "path": files[0]["filename"] if files else "N/A",
            "line": 1,
            "side": "RIGHT",
            "body": "✅ No issues found in this PR.",
        }])

if __name__ == "__main__":
    main()
