#!/usr/bin/env python3
"""
Create Submission Zip for Ex5

Creates a submission zip according to ex5.md:
- Zip file named <ID>.zip, where ID is the submitting student's ID
- Top-level ids.txt with one team member ID per line
- Top-level ex5/ directory containing source code and Makefile
- ex5/Makefile must build ex5/COMPILER

Examples:
    python3 create_ex5_submission.py /path/to/ex5
    python3 create_ex5_submission.py /path/to/ex5 --id 123456789
    python3 create_ex5_submission.py /path/to/ex5 --ids 111111111 222222222
    python3 create_ex5_submission.py /path/to/ex5 --id 123456789 --output .
"""

import argparse
import fnmatch
import pathlib
import shutil
import sys
import tempfile
import zipfile


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}\n")


def print_success(text):
    print(f"{Colors.GREEN}[OK] {text}{Colors.END}")


def print_error(text):
    print(f"{Colors.RED}[ERROR] {text}{Colors.END}")


def print_warning(text):
    print(f"{Colors.YELLOW}[WARN] {text}{Colors.END}")


def print_info(text):
    print(f"{Colors.BLUE}[INFO] {text}{Colors.END}")


REQUIRED_PATHS = [
    "Makefile",
    "manifest",
    "jflex",
    "cup",
    "external_jars",
    "src",
]

OPTIONAL_PATHS = [
    "lib",
    "resources",
]

IGNORE_PATTERNS = [
    ".git",
    ".gitignore",
    "__pycache__",
    "*.class",
    "*.o",
    "*.so",
    "*.a",
    "*.swp",
    "*.swo",
    ".DS_Store",
    "Thumbs.db",
    "Lexer.java",
    "Parser.java",
    "TokenNames.java",
    "sym.java",
    "COMPILER",
    "PARSER",
    "SEMANT",
    "ANALYZER",
    "LEXER",
    "MIPS.txt",
    "MIPS OUTPUT.txt",
    "output",
    "expected_output",
    "input",
]


def path_is_ignored(path, ignore_patterns):
    name = path.name
    rel = str(path)
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern) for pattern in ignore_patterns)


def validate_student_ids(ids):
    valid_ids = []
    for student_id in ids:
        student_id = student_id.strip()
        if not student_id:
            continue
        if not student_id.isdigit():
            print_warning(f"ID '{student_id}' is not numeric, skipping")
            continue
        valid_ids.append(student_id)
    return valid_ids


def get_student_ids_interactive():
    print_info("Enter student IDs one per line. Submit an empty line to finish.")
    ids = []
    while True:
        try:
            student_id = input(f"  ID {len(ids) + 1}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not student_id:
            break
        if not student_id.isdigit():
            print_warning("ID must be numeric")
            continue
        ids.append(student_id)
    return ids


def validate_ex5_directory(ex5_path):
    if not ex5_path.exists():
        return False, f"Directory does not exist: {ex5_path}"
    if not ex5_path.is_dir():
        return False, f"Path is not a directory: {ex5_path}"
    if not (ex5_path / "Makefile").exists():
        return False, "Makefile not found in ex5 directory"

    source_patterns = ["**/*.java", "**/*.lex", "**/*.cup", "**/*.py", "**/*.c", "**/*.cpp"]
    source_files = []
    for pattern in source_patterns:
        source_files.extend(ex5_path.glob(pattern))

    source_files = [p for p in source_files if not any(part.startswith(".") for part in p.parts)]
    if not source_files:
        print_warning("No source files (.java, .lex, .cup, .py, .c, .cpp) found")
        response = input("Continue anyway? (y/n): ").strip().lower()
        if response != "y":
            return False, "No source files found"

    return True, None


def copy_tree_filtered(src_path, dest_path, ignore_patterns):
    if path_is_ignored(src_path, ignore_patterns):
        return

    if src_path.is_file():
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_path)
        return

    if src_path.is_dir():
        dest_path.mkdir(parents=True, exist_ok=True)
        for child in src_path.iterdir():
            copy_tree_filtered(child, dest_path / child.name, ignore_patterns)


def copy_required_files(src_dir, dest_dir, extra_paths=None):
    dest_dir.mkdir(parents=True, exist_ok=True)
    include_paths = list(REQUIRED_PATHS) + list(OPTIONAL_PATHS)
    if extra_paths:
        include_paths.extend(extra_paths)

    copied_any = False
    for rel_path in include_paths:
        src_path = src_dir / rel_path
        if not src_path.exists():
            continue
        copy_tree_filtered(src_path, dest_dir / rel_path, IGNORE_PATTERNS)
        copied_any = True

    if not copied_any:
        raise RuntimeError("No required ex5 files were copied")


def write_ids_file(path, student_ids):
    with open(path, "w", encoding="utf-8") as ids_file:
        for student_id in student_ids:
            ids_file.write(f"{student_id}\n")


def create_submission_zip(ex5_path, student_ids, output_dir=None, extra_paths=None):
    if not student_ids:
        raise ValueError("At least one student ID is required")

    output_dir = pathlib.Path(output_dir) if output_dir else pathlib.Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_path = output_dir / f"{student_ids[0]}.zip"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = pathlib.Path(temp_dir)
        ids_file = temp_path / "ids.txt"
        ex5_dest = temp_path / "ex5"

        write_ids_file(ids_file, student_ids)
        print_success(f"Created ids.txt with {len(student_ids)} ID(s)")

        print_info(f"Copying required files from {ex5_path}")
        copy_required_files(ex5_path, ex5_dest, extra_paths=extra_paths)
        print_success("Copied ex5 source files")

        print_info(f"Creating {zip_path.name}")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(ids_file, "ids.txt")
            for file_path in sorted(ex5_dest.rglob("*")):
                if file_path.is_file():
                    zipf.write(file_path, file_path.relative_to(temp_path))

    return zip_path


def verify_zip_contents(zip_path):
    print_info(f"Verifying {zip_path.name}")
    with zipfile.ZipFile(zip_path, "r") as zipf:
        names = zipf.namelist()

    required = ["ids.txt", "ex5/Makefile"]
    for name in required:
        if name not in names:
            print_error(f"{name} not found in zip")
            return False

    ex5_files = [name for name in names if name.startswith("ex5/")]
    if not ex5_files:
        print_error("ex5/ directory not found in zip")
        return False

    forbidden = [
        "ex5/COMPILER",
        "ex5/MIPS.txt",
        "ex5/MIPS OUTPUT.txt",
    ]
    forbidden_found = [name for name in forbidden if name in names]
    if forbidden_found:
        print_error(f"Generated artifacts found in zip: {', '.join(forbidden_found)}")
        return False

    print_success("Zip structure validated")
    print(f"  ids.txt")
    print(f"  ex5/ directory with {len(ex5_files)} file(s)")
    print(f"  ex5/Makefile")
    return True


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create ex5 submission zip",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 create_ex5_submission.py ./ex5 --id 123456789
  python3 create_ex5_submission.py ~/compilation/ex5 --ids 111111111 222222222
  python3 create_ex5_submission.py ./ex5 --id 123456789 --output .
  python3 create_ex5_submission.py ./ex5 --id 123456789 --include README.md
        """,
    )
    parser.add_argument("ex5_directory", help="Path to ex5 directory containing source code and Makefile")
    parser.add_argument("--id", help="Single student ID")
    parser.add_argument("--ids", nargs="+", help="Multiple student IDs")
    parser.add_argument("--output", "-o", help="Output directory for zip file, default: current directory")
    parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing zip without prompting")
    parser.add_argument(
        "--include",
        nargs="+",
        default=[],
        help="Additional paths inside ex5/ to include in the zip",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    print_header("EX5 SUBMISSION ZIP CREATOR")

    ex5_path = pathlib.Path(args.ex5_directory).expanduser().resolve()
    print_info(f"Ex5 directory: {ex5_path}")

    valid, error = validate_ex5_directory(ex5_path)
    if not valid:
        print_error(f"Invalid ex5 directory: {error}")
        return 1
    print_success("Ex5 directory validated")

    if args.id:
        student_ids = [args.id]
    elif args.ids:
        student_ids = args.ids
    else:
        student_ids = get_student_ids_interactive()

    student_ids = validate_student_ids(student_ids)
    if not student_ids:
        print_error("No valid student IDs provided")
        return 1

    output_dir = pathlib.Path(args.output).expanduser() if args.output else pathlib.Path.cwd()
    zip_path = output_dir / f"{student_ids[0]}.zip"
    if zip_path.exists() and not args.force:
        print_warning(f"Zip file already exists: {zip_path}")
        response = input("Overwrite? (y/n): ").strip().lower()
        if response != "y":
            print_info("Aborted")
            return 0

    try:
        zip_path = create_submission_zip(
            ex5_path,
            student_ids,
            output_dir=output_dir,
            extra_paths=args.include,
        )
    except Exception as exc:
        print_error(f"Failed to create zip file: {exc}")
        return 1

    if not verify_zip_contents(zip_path):
        return 1

    print_header("SUBMISSION READY")
    print_success(f"Zip file created: {zip_path}")
    print_info(f"File size: {zip_path.stat().st_size / 1024:.1f} KB")
    print()
    print("Next steps:")
    print("  1. Place the zip next to the self-check script.")
    print("  2. Run: python3 tests-runner.py")
    print(f"  3. Submit {zip_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
