import os
import glob
import subprocess

def scrub_files():
    secret = "qk27l6s9esjj5j49iqi43852ktfrgmiq"
    for root, dirs, files in os.walk("."):
        if ".git" in root or ".venv" in root:
            continue
        for file in files:
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if secret in content:
                    new_content = content.replace(secret, "")
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
            except Exception:
                pass

if __name__ == "__main__":
    scrub_files()
