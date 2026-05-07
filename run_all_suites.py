#!/usr/bin/env python3
"""Run all compiler exercise test suites through their existing phase runners."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
EXERCISE_DIR = TESTS_DIR / "ex5"
MAKEFILE_PATH = EXERCISE_DIR / "Makefile"
EXECUTABLE_PATH = EXERCISE_DIR / "COMPILER"


@dataclass(frozen=True)
class Phase:
    id: str
    name: str
    script: Path
    path_args: tuple[str, ...]


PHASES: tuple[Phase, ...] = (
    Phase(
        id="ex1",
        name="Exercise 1 lexical",
        script=TESTS_DIR / "ex1_lexical" / "run_lexical_suite.py",
        path_args=("--root", str(TESTS_DIR / "ex1_lexical")),
    ),
    Phase(
        id="ex2",
        name="Exercise 2 parsing",
        script=TESTS_DIR / "ex2_parsing" / "run_parsing_suite.py",
        path_args=("--root", str(TESTS_DIR / "ex2_parsing")),
    ),
    Phase(
        id="ex3",
        name="Exercise 3 semantic",
        script=TESTS_DIR / "ex3_semantic" / "run_semantic_suite.py",
        path_args=("--root", str(TESTS_DIR / "ex3_semantic")),
    ),
    Phase(
        id="ex4",
        name="Exercise 4 analysis",
        script=TESTS_DIR / "ex4_analysis" / "run_analysis_suite.py",
        path_args=("--root", str(TESTS_DIR / "ex4_analysis" / "well_defined_behavior")),
    ),
    Phase(
        id="ex5",
        name="Exercise 5 code generation",
        script=TESTS_DIR / "ex5_codegen" / "run_codegen_suite.py",
        path_args=(
            "--inputs",
            str(TESTS_DIR / "ex5_codegen" / "unofficial" / "inputs"),
            "--expected",
            str(TESTS_DIR / "ex5_codegen" / "unofficial" / "expected"),
            "--coverage-index",
            str(TESTS_DIR / "ex5_codegen" / "coverage-index.csv"),
        ),
    ),
)


PHASE_BY_ID = {phase.id: phase for phase in PHASES}


@dataclass(frozen=True)
class PhaseResult:
    phase: Phase
    return_code: int
    elapsed_seconds: float


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spim", default="spim")
    parser.add_argument(
        "--phase",
        action="append",
        choices=tuple(PHASE_BY_ID),
        help="Run one phase. May be repeated. Omit to run ex1 through ex5.",
    )
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--keep-temp", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    phases = selected_phases(args.phase)
    setup_error = validate_phase_scripts(phases)
    if setup_error is not None:
        print(f"usage error: {setup_error}", file=sys.stderr)
        return 2

    try:
        compiler = prepare_compiler_from_archive()
    except Exception as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 2

    results = [run_phase(phase, args, compiler) for phase in phases]
    print_summary(results)

    if any(result.return_code == 2 for result in results):
        return 2
    if any(result.return_code != 0 for result in results):
        return 1
    return 0


def selected_phases(phase_ids: list[str] | None) -> list[Phase]:
    if not phase_ids:
        return list(PHASES)

    phases: list[Phase] = []
    seen: set[str] = set()
    for phase_id in phase_ids:
        if phase_id in seen:
            continue
        phases.append(PHASE_BY_ID[phase_id])
        seen.add(phase_id)
    return phases


def validate_phase_scripts(phases: list[Phase]) -> str | None:
    for phase in phases:
        if not phase.script.is_file():
            return f"phase runner not found for {phase.id}: {phase.script}"
    return None


def prepare_compiler_from_archive() -> Path:
    archive = find_single_submission_archive()
    unzip_archive(archive)
    run_make()
    if not EXECUTABLE_PATH.is_file():
        raise FileNotFoundError(f"compiler not found after make: {EXECUTABLE_PATH}")
    return EXECUTABLE_PATH.resolve()


def find_single_submission_archive() -> Path:
    zip_files = sorted(path for path in TESTS_DIR.glob("*.zip") if path.stem.isdigit())
    if not zip_files:
        raise FileNotFoundError("no numeric submission zip archive found")
    if len(zip_files) > 1:
        names = ", ".join(path.name for path in zip_files)
        raise RuntimeError(f"more than one numeric submission zip archive found: {names}")
    return zip_files[0]


def unzip_archive(archive: Path) -> None:
    print(f"Unzipping archive: {archive.name}", flush=True)
    with zipfile.ZipFile(archive, "r") as zip_ref:
        zip_ref.extractall(TESTS_DIR)
    print("Unzip complete.", flush=True)


def run_make() -> None:
    if not MAKEFILE_PATH.is_file():
        raise FileNotFoundError(f"required Makefile not found: {MAKEFILE_PATH}")

    print("Running make in ex5...", flush=True)
    completed = subprocess.run(
        ["make"],
        cwd=str(EXERCISE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        print("--- MAKE FAILED ---", file=sys.stderr)
        print("--- STDOUT ---", file=sys.stderr)
        print(completed.stdout, file=sys.stderr)
        print("--- STDERR ---", file=sys.stderr)
        print(completed.stderr, file=sys.stderr)
        raise RuntimeError("make failed")

    print("make successful.", flush=True)


def run_phase(phase: Phase, args: argparse.Namespace, compiler: Path) -> PhaseResult:
    command = build_command(phase, args, compiler)

    print()
    print(f"=== {phase.id}: {phase.name} ===", flush=True)
    started = time.monotonic()
    completed = subprocess.run(command, cwd=str(TESTS_DIR))
    elapsed_seconds = time.monotonic() - started
    print(
        f"=== {phase.id}: exit {completed.returncode} "
        f"({elapsed_seconds:.1f}s) ===",
        flush=True,
    )
    return PhaseResult(phase, completed.returncode, elapsed_seconds)


def build_command(phase: Phase, args: argparse.Namespace, compiler: Path) -> list[str]:
    command = [
        sys.executable,
        str(phase.script),
        "--compiler",
        str(compiler),
        "--spim",
        args.spim,
        *phase.path_args,
    ]

    if args.timeout is not None:
        command.extend(("--timeout", str(args.timeout)))
    if args.keep_temp:
        command.append("--keep-temp")

    return command


def print_summary(results: list[PhaseResult]) -> None:
    print()
    print("=== combined summary ===")
    for result in results:
        status = "PASS" if result.return_code == 0 else "FAIL"
        print(
            f"{status} {result.phase.id} {result.phase.name} "
            f"(exit {result.return_code}, {result.elapsed_seconds:.1f}s)"
        )

    passed = sum(1 for result in results if result.return_code == 0)
    print(f"summary: {passed}/{len(results)} phases passed")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
