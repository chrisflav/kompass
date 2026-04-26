#!/usr/bin/env python3
"""Post-process test container output for quiet mode reporting."""

import os
import re
import sys


def main():
    htmlcov_dir = sys.argv[1] if len(sys.argv) > 1 else "htmlcov"

    status_file = os.path.join(htmlcov_dir, "run_status.txt")
    if not os.path.exists(status_file):
        print("Container setup failed or was aborted.")
        sys.exit(1)

    with open(status_file) as f:
        if f.read().strip() != "ok":
            print("Container setup failed or was aborted.")
            sys.exit(1)

    exit_code_file = os.path.join(htmlcov_dir, "test_exit_code.txt")
    with open(exit_code_file) as f:
        test_failed = int(f.read().strip()) != 0

    test_output_file = os.path.join(htmlcov_dir, "test_output.txt")
    if test_failed:
        blocks = extract_failure_blocks(test_output_file)
        print("The following tests failed:")
        print()
        if blocks:
            print("\n".join(blocks))
        else:
            with open(test_output_file) as f:
                print(f.read())
    else:
        print("All tests passed.")

    coverage_file = os.path.join(htmlcov_dir, "coverage_report.txt")
    missing = parse_coverage_report(coverage_file)
    if missing:
        print()
        print("The following lines are not covered by tests:")
        print()
        for filename, lines in missing:
            print(f"  {filename}: {lines}")
    else:
        print("Coverage is at 100%.")

    sys.exit(1 if (test_failed or missing) else 0)


def extract_failure_blocks(test_output_file):
    with open(test_output_file) as f:
        content = f.read()

    # Each failure block starts with ===...===\nFAIL: or ERROR: and ends
    # before the next ===...=== or the ---...---\nRan summary line.
    pattern = re.compile(
        r"={70}\n(?:FAIL|ERROR):.*?(?=\n={70}|\n-{70}\nRan )",
        re.DOTALL,
    )
    return pattern.findall(content)


def parse_coverage_report(coverage_file):
    if not os.path.exists(coverage_file):
        return []

    missing = []
    with open(coverage_file) as f:
        for line in f:
            parts = line.split()
            if not parts or parts[0].startswith("-") or parts[0] in ("Name", "TOTAL"):
                continue
            if len(parts) >= 5:
                try:
                    if int(parts[2]) > 0:
                        missing.append((parts[0], " ".join(parts[4:])))
                except ValueError:
                    pass
    return missing


if __name__ == "__main__":
    main()
