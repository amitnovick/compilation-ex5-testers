#!/usr/bin/env python3
"""Run the Exercise 5 code generation test suite."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

EX5_REQUIREMENTS = {
    "FR-001",
    "FR-002",
    "FR-003",
    "FR-004",
    "FR-005",
    "FR-006",
    "FR-007",
    "FR-008",
    "FR-009",
    "FR-010",
    "FR-011",
    "FR-012",
    "FR-013",
    "FR-014",
}

REQUIRED_EX5_TOPICS = {
    "ir function calls",
    "ir global initialization order",
    "ir binary operand order",
    "ir assignment operand order",
    "ir object construction",
    "ir array load store",
    "ir method dispatch",
    "ir string concat equality",
    "ir control flow",
    "ir return prologue epilogue",
    "allocation colorable program",
    "allocation near limit pressure",
    "allocation failure",
    "allocation loop carried values",
    "allocation call live values",
    "allocation branch join",
    "allocation scratch registers",
    "allocation object field pressure",
    "allocation nested expression pressure",
    "allocation t register compliance",
    "mips library syscalls",
    "mips heap allocation",
    "mips string behavior",
    "mips array behavior",
    "mips class behavior",
    "mips equality behavior",
    "mips inheritance dispatch",
    "mips recursion",
    "mips functions returns",
    "mips globals",
    "mips if while",
    "mips mixed behavior",
    "runtime saturation addition",
    "runtime saturation subtraction",
    "runtime saturation multiplication",
    "runtime division floor",
    "runtime left to right function arguments",
    "runtime left to right binary operands",
    "runtime left to right assignments",
    "runtime left to right global initializers",
    "runtime division by zero",
    "runtime invalid pointer",
    "runtime access violation negative index",
    "runtime access violation length index",
    "runtime access violation side effect index",
}

DEFAULT_TIMEOUT_SECONDS = 10.0
ALLOWED_TEMP_REGISTERS = {f"$t{i}" for i in range(10)}
RUNTIME_ERROR_MESSAGES = (
    "Illegal Division By Zero",
    "Invalid Pointer Dereference",
    "Access Violation",
)
SPIM_BANNER_LINES = (
    "SPIM Version 8.0 of January 8, 2010",
    "Copyright 1990-2010, James R. Larus.",
    "All Rights Reserved.",
    "See the file README for a full copyright notice.",
    "Loaded: /usr/lib/spim/exceptions.s",
)
EX5_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ExecutionResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


@dataclass(frozen=True)
class ExpectedOutput:
    compiler: dict[str, Any]
    generated: dict[str, Any] = field(default_factory=dict)
    spim: dict[str, Any] | None = None
    raw_text: str | None = None


@dataclass(frozen=True)
class TestCase:
    id: str
    coverage_target: str
    pipeline_stage: str
    input_path: Path
    expected_path: Path
    run_spim: bool
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class OfficialCase:
    id: str
    input_path: Path
    expected_path: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class CoverageIndexRow:
    test_id: str
    requirement_id: str
    ex5_topic: str
    prior_exercises_excluded: bool


class RunnerAssertionError(AssertionError):
    """Assertion failure that carries enough context for the runner summary."""


CASE_REGISTRY: tuple[dict[str, object], ...] = (
    {
        "id": "ir_left_to_right_arguments_preserves_order",
        "coverage_target": "IR generation for left-to-right argument evaluation",
        "pipeline_stage": "ir",
        "input": "ir/left_to_right_arguments.l",
        "expected": "ir/left_to_right_arguments.json",
        "run_spim": False,
    },
    {
        "id": "ir_object_array_operations_generate_expected_structure",
        "coverage_target": "IR generation for object and array operations",
        "pipeline_stage": "ir",
        "input": "ir/object_array_operations.l",
        "expected": "ir/object_array_operations.json",
        "run_spim": False,
    },
    {
        "id": "allocation_colorable_temporaries_use_only_t_registers",
        "coverage_target": "Liveness and register allocation success within 10 registers",
        "pipeline_stage": "allocation",
        "input": "allocation/colorable_temporaries.l",
        "expected": "allocation/colorable_temporaries.json",
        "run_spim": False,
    },
    {
        "id": "allocation_pressure_reports_register_allocation_failed",
        "coverage_target": "Register allocation failure output",
        "pipeline_stage": "allocation",
        "input": "allocation/register_allocation_fails.l",
        "expected": "allocation/register_allocation_fails.txt",
        "run_spim": False,
    },
    {
        "id": "mips_library_and_heap_runs_under_spim",
        "coverage_target": "MIPS translation for library printing and heap allocation",
        "pipeline_stage": "mips",
        "input": "mips/library_and_heap.l",
        "expected": "mips/library_and_heap.txt",
        "run_spim": True,
    },
    {
        "id": "mips_equality_and_assignment_match_runtime_contract",
        "coverage_target": "MIPS translation for equality and assignment behavior",
        "pipeline_stage": "mips",
        "input": "mips/equality_and_assignment.l",
        "expected": "mips/equality_and_assignment.txt",
        "run_spim": True,
    },
    {
        "id": "runtime_saturation_arithmetic_clamps_bounds",
        "coverage_target": "Saturation arithmetic bounds",
        "pipeline_stage": "runtime",
        "input": "runtime/saturation_arithmetic.l",
        "expected": "runtime/saturation_arithmetic.txt",
        "run_spim": True,
    },
    {
        "id": "runtime_left_to_right_evaluation_observable",
        "coverage_target": "Left-to-right runtime evaluation",
        "pipeline_stage": "runtime",
        "input": "runtime/left_to_right_runtime.l",
        "expected": "runtime/left_to_right_runtime.txt",
        "run_spim": True,
    },
    {
        "id": "runtime_division_by_zero_reports_exact_message",
        "coverage_target": "Division by zero runtime error",
        "pipeline_stage": "runtime",
        "input": "runtime/division_by_zero.l",
        "expected": "runtime/division_by_zero.txt",
        "run_spim": True,
    },
    {
        "id": "runtime_invalid_pointer_reports_exact_message",
        "coverage_target": "Invalid pointer dereference runtime error",
        "pipeline_stage": "runtime",
        "input": "runtime/invalid_pointer.l",
        "expected": "runtime/invalid_pointer.txt",
        "run_spim": True,
    },
    {
        "id": "runtime_access_violation_reports_exact_message",
        "coverage_target": "Out-of-bounds array access runtime error",
        "pipeline_stage": "runtime",
        "input": "runtime/access_violation.l",
        "expected": "runtime/access_violation.txt",
        "run_spim": True,
    },
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--spim", default="spim")
    parser.add_argument("--inputs", default=EX5_DIR / "unofficial" / "inputs", type=Path)
    parser.add_argument("--expected", default=EX5_DIR / "unofficial" / "expected", type=Path)
    parser.add_argument(
        "--coverage-index",
        default=EX5_DIR / "coverage-index.csv",
        type=Path,
    )
    parser.add_argument("--official-root", default=EX5_DIR / "official-tests", type=Path)
    parser.add_argument("--skip-official", action="store_true")
    parser.add_argument("--case")
    parser.add_argument("--category", choices=("ir", "allocation", "mips", "runtime"))
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--keep-temp", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        if not args.compiler.exists():
            raise FileNotFoundError(f"compiler not found: {args.compiler}")
        cases = load_cases(
            args.inputs,
            args.expected,
            args.coverage_index,
            category=args.category,
            case_id=args.case,
            timeout_seconds=args.timeout,
        )
        official_cases = []
        if not args.skip_official and args.category is None and args.case is None:
            official_cases = load_official_cases(
                args.official_root,
                timeout_seconds=args.timeout,
            )
    except Exception as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    for case in cases:
        try:
            run_case(case, args.compiler, args.spim, args.keep_temp)
            print(f"PASS {case.id}")
        except RunnerAssertionError as exc:
            failures.append(str(exc))
            print(f"FAIL {case.id}", file=sys.stderr)
            print(exc, file=sys.stderr)
        except Exception as exc:
            failures.append(f"{case.id}: {exc}")
            print(f"ERROR {case.id}: {exc}", file=sys.stderr)

    unofficial_failures = len(failures)
    if cases and official_cases:
        print(f"summary: {len(cases) - unofficial_failures}/{len(cases)} unofficial passed")

    for case in official_cases:
        try:
            run_official_case(case, args.compiler, args.spim)
            print(f"PASS official_{case.id}")
        except RunnerAssertionError as exc:
            failures.append(str(exc))
            print(f"FAIL official_{case.id}", file=sys.stderr)
            print(exc, file=sys.stderr)
        except Exception as exc:
            failures.append(f"official_{case.id}: {exc}")
            print(f"ERROR official_{case.id}: {exc}", file=sys.stderr)

    total = len(cases) + len(official_cases)
    passed = total - len(failures)
    if official_cases:
        official_failures = len(failures) - unofficial_failures
        print(
            f"summary: {len(official_cases) - official_failures}/"
            f"{len(official_cases)} official passed"
        )
    print(f"summary: {passed}/{total} passed")
    if failures:
        return 1
    return 0


def load_cases(
    inputs_root: Path,
    expected_root: Path,
    coverage_index: Path,
    *,
    category: str | None = None,
    case_id: str | None = None,
    timeout_seconds: float | None = None,
) -> list[TestCase]:
    rows = load_coverage_index(coverage_index)
    validate_coverage(rows)

    covered_ids = {row.test_id for row in rows}
    registry_items = list(CASE_REGISTRY)
    registered_ids = {str(item["id"]) for item in registry_items}
    for row in rows:
        if row.test_id not in registered_ids:
            registry_items.append(case_item_from_coverage_row(row))
            registered_ids.add(row.test_id)

    cases: list[TestCase] = []
    for item in registry_items:
        item_id = str(item["id"])
        stage = str(item["pipeline_stage"])
        if category and stage != category:
            continue
        if case_id and item_id != case_id:
            continue
        if item_id not in covered_ids:
            raise ValueError(f"coverage-index.csv has no row for test case {item_id}")
        cases.append(
            TestCase(
                id=item_id,
                coverage_target=str(item["coverage_target"]),
                pipeline_stage=stage,
                input_path=inputs_root / str(item["input"]),
                expected_path=expected_root / str(item["expected"]),
                run_spim=bool(item["run_spim"]),
                timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
            )
        )

    if case_id and not cases:
        raise ValueError(f"unknown test case: {case_id}")
    if category and not cases:
        raise ValueError(f"no test cases selected for category: {category}")

    for case in cases:
        if not case.input_path.is_file():
            raise FileNotFoundError(f"missing input for {case.id}: {case.input_path}")
        if not case.expected_path.is_file():
            raise FileNotFoundError(f"missing expected output for {case.id}: {case.expected_path}")
    return cases


def load_official_cases(
    official_root: Path,
    *,
    timeout_seconds: float | None = None,
) -> list[OfficialCase]:
    input_root = official_root / "input"
    expected_root = official_root / "expected_output"
    if not input_root.is_dir():
        raise FileNotFoundError(f"missing official input root: {input_root}")
    if not expected_root.is_dir():
        raise FileNotFoundError(f"missing official expected root: {expected_root}")

    cases: list[OfficialCase] = []
    for input_path in sorted(input_root.glob("*.txt")):
        expected_path = expected_root / f"{input_path.stem}_Expected_Output.txt"
        if not expected_path.is_file():
            raise FileNotFoundError(
                f"missing official expected output for {input_path.stem}: {expected_path}"
            )
        cases.append(
            OfficialCase(
                id=input_path.stem,
                input_path=input_path,
                expected_path=expected_path,
                timeout_seconds=timeout_seconds or DEFAULT_TIMEOUT_SECONDS,
            )
        )
    if not cases:
        raise ValueError(f"no official tests found under {input_root}")
    return cases


def case_item_from_coverage_row(row: CoverageIndexRow) -> dict[str, object]:
    try:
        stage, stem = row.test_id.split("_", 1)
    except ValueError as exc:
        raise ValueError(
            f"coverage-index.csv test case {row.test_id} is not registered and "
            "does not follow <category>_<input-stem>"
        ) from exc
    if stage not in {"ir", "allocation", "mips", "runtime"}:
        raise ValueError(
            f"coverage-index.csv test case {row.test_id} uses unknown category {stage}"
        )
    return {
        "id": row.test_id,
        "coverage_target": row.ex5_topic,
        "pipeline_stage": stage,
        "input": f"{stage}/{stem}.l",
        "expected": f"{stage}/{stem}{expected_suffix_for(row)}",
        "run_spim": stage in {"mips", "runtime"},
    }


def expected_suffix_for(row: CoverageIndexRow) -> str:
    test_id = row.test_id
    stage = test_id.split("_", 1)[0]
    if stage in {"mips", "runtime"}:
        return ".txt"
    if row.requirement_id == "FR-004" or "failure" in row.ex5_topic.lower():
        return ".txt"
    return ".json"


def load_expected(case: TestCase) -> ExpectedOutput:
    text = case.expected_path.read_text(encoding="utf-8")
    suffix = case.expected_path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(text)
        if "cases" in payload:
            try:
                payload = payload["cases"][case.id]
            except KeyError as exc:
                raise KeyError(f"{case.expected_path} has no expectation for {case.id}") from exc
        return ExpectedOutput(
            compiler=payload.get("compiler", {}),
            generated=payload.get("generated", {}),
            spim=payload.get("spim"),
        )
    if suffix == ".txt":
        return ExpectedOutput(compiler={}, generated={}, spim=None, raw_text=text)
    raise ValueError(f"unsupported expected-output file extension: {case.expected_path}")


def load_coverage_index(path: Path) -> list[CoverageIndexRow]:
    if not path.is_file():
        raise FileNotFoundError(f"missing coverage index: {path}")
    rows: list[CoverageIndexRow] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            rows.append(
                CoverageIndexRow(
                    test_id=raw["test_id"],
                    requirement_id=raw["requirement_id"],
                    ex5_topic=raw["ex5_topic"],
                    prior_exercises_excluded=parse_bool(raw["prior_exercises_excluded"]),
                )
            )
    return rows


def validate_coverage(rows: list[CoverageIndexRow]) -> None:
    if not rows:
        raise ValueError("coverage-index.csv must contain at least one row")
    topics = {row.ex5_topic for row in rows}
    missing_topics = sorted(REQUIRED_EX5_TOPICS - topics)
    if missing_topics:
        raise ValueError(
            "coverage-index.csv is missing required Exercise 5 behavior-family "
            f"coverage: {', '.join(missing_topics)}"
        )
    for row in rows:
        if row.requirement_id not in EX5_REQUIREMENTS:
            raise ValueError(
                f"{row.test_id} maps to unsupported requirement {row.requirement_id}"
            )
        if not row.prior_exercises_excluded:
            raise ValueError(f"{row.test_id} does not exclude prior exercise scope")
        lowered = row.ex5_topic.lower()
        if any(term in lowered for term in ("lexical", "syntax", "semantic")):
            raise ValueError(f"{row.test_id} maps to prior-exercise topic {row.ex5_topic}")


def run_case(case: TestCase, compiler: Path, spim_command: str, keep_temp: bool) -> None:
    expected = load_expected(case)
    with isolated_work_dir(case, keep_temp) as work_dir:
        output_file = generated_output_path(work_dir, case)
        expected_text = expected.raw_text.rstrip("\n") if expected.raw_text is not None else None

        compiler_result = run_compiler(
            compiler=compiler,
            input_file=case.input_path,
            output_file=output_file,
            timeout_seconds=case.timeout_seconds,
        )
        if expected.raw_text is not None:
            assert_raw_compiler_success(case, compiler_result)
        else:
            assert_process_observation(case, "compiler", compiler_result, expected.compiler)
            assert_generated_output(case, output_file, expected)

        generated_text = output_file.read_text(encoding="utf-8") if output_file.exists() else ""
        allocation_failed = assert_register_allocation_failure_guard(case, generated_text)
        if allocation_failed:
            if expected.raw_text is not None:
                assert_raw_text(case, "generated", expected_text, generated_text)
            return
        if case.run_spim and generated_text.strip() == "ERROR":
            raise RunnerAssertionError(
                f"{case.id} [{case.pipeline_stage}] failed at generated\n"
                f"input: {case.input_path}\n"
                f"expected: runnable MIPS assembly\n"
                f"observed: 'ERROR'"
            )

        if case.run_spim:
            if expected.raw_text is not None:
                spim_result = run_spim(spim_command, output_file, case.timeout_seconds)
                assert_raw_spim_stdout(case, spim_result, expected_text)
                return
            if expected.spim is None:
                raise RunnerAssertionError(f"{case.id} runs SPIM but has no SPIM expectation")
            spim_result = run_spim(spim_command, output_file, case.timeout_seconds)
            assert_process_observation(case, "spim", spim_result, expected.spim)
            return

        if expected.raw_text is not None:
            assert_raw_text(case, "generated", expected_text, generated_text)


def run_official_case(case: OfficialCase, compiler: Path, spim_command: str) -> None:
    expected_text = case.expected_path.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix=f"official_{case.id}-") as temp_dir:
        output_file = Path(temp_dir) / f"{case.id}.txt"
        compiler_result = run_compiler(
            compiler=compiler,
            input_file=case.input_path,
            output_file=output_file,
            timeout_seconds=case.timeout_seconds,
        )
        if compiler_result.timed_out:
            fail_official(case, "compiler", "process completed before timeout", "timed out")
        if not output_file.exists():
            fail_official(case, "compiler", f"{output_file} exists", "missing")

        generated_text = output_file.read_text(encoding="utf-8")
        if generated_text == "Register Allocation Failed":
            assert_official_text(case, "generated", expected_text, generated_text)
            return

        spim_result = run_spim(spim_command, output_file, case.timeout_seconds)
        if spim_result.timed_out:
            fail_official(case, "spim", "process completed before timeout", "timed out")
        if spim_result.exit_code != 0:
            fail_official(case, "spim", "exit code 0", spim_result.exit_code)
        assert_official_text(case, "spim", expected_text, spim_result.stdout)


@contextmanager
def isolated_work_dir(case: TestCase, keep_temp: bool = False) -> Iterator[Path]:
    if keep_temp:
        path = Path(tempfile.mkdtemp(prefix=f"{case.id}-"))
        try:
            yield path
        finally:
            print(f"kept temp directory for {case.id}: {path}")
        return

    manager = tempfile.TemporaryDirectory(prefix=f"{case.id}-")
    path = Path(manager.name)
    try:
        yield path
    finally:
        manager.cleanup()


def generated_output_path(work_dir: Path, case: TestCase) -> Path:
    return work_dir / f"{case.id}.mips"


def run_compiler(
    compiler: Path,
    input_file: Path,
    output_file: Path,
    timeout_seconds: float,
) -> ExecutionResult:
    command = ["java", "-jar", str(compiler), str(input_file), str(output_file)]
    return run_process(command, timeout_seconds)


def run_spim(spim: str, mips_file: Path, timeout_seconds: float) -> ExecutionResult:
    command = [spim, "-file", str(mips_file)]
    return run_process(command, timeout_seconds)


def run_process(command: Sequence[str], timeout_seconds: float) -> ExecutionResult:
    start = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return ExecutionResult(
            command=tuple(command),
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return ExecutionResult(
            command=tuple(command),
            stdout=stdout,
            stderr=stderr,
            exit_code=-1,
            duration_ms=duration_ms,
            timed_out=True,
        )


def assert_process_observation(
    case: TestCase,
    stage: str,
    result: ExecutionResult,
    expected: dict[str, Any],
) -> None:
    if result.timed_out:
        fail(case, stage, "process completed before timeout", "timed out")
    if "exit_code" in expected and result.exit_code != expected["exit_code"]:
        fail(case, stage, f"exit code {expected['exit_code']}", result.exit_code)
    assert_stream(case, stage, "stdout", result.stdout, expected)
    assert_stream(case, stage, "stderr", result.stderr, expected)


def assert_generated_output(
    case: TestCase,
    generated_file: Path,
    expected: ExpectedOutput,
) -> None:
    generated = expected.generated
    if not generated:
        return

    if generated.get("exists") and not generated_file.exists():
        fail(case, "generated", f"{generated_file} exists", "missing")

    text = generated_file.read_text(encoding="utf-8") if generated_file.exists() else ""

    if generated.get("non_empty") and not text.strip():
        fail(case, "generated", "non-empty generated output", "empty output")

    if "exact_text" in generated and text != generated["exact_text"]:
        fail(case, "generated", generated["exact_text"], text)

    for needle in as_list(generated.get("contains")):
        if needle not in text:
            fail(case, "generated", f"output containing {needle!r}", text)

    for needle in as_list(generated.get("not_contains")):
        if needle in text:
            fail(case, "generated", f"output without {needle!r}", text)

    for pattern in as_list(generated.get("regex")):
        if re.search(pattern, text, flags=re.MULTILINE) is None:
            fail(case, "generated", f"output matching /{pattern}/", text)

    if generated.get("allowed_registers_only"):
        assert_allowed_temp_registers(case, text)

    for message in as_list(generated.get("runtime_messages")):
        if message not in RUNTIME_ERROR_MESSAGES:
            fail(case, "generated", "known Exercise 5 runtime message", message)


def assert_register_allocation_failure_guard(case: TestCase, output_text: str) -> bool:
    if "Register Allocation Failed" in output_text:
        if case.run_spim:
            fail(case, "compiler", "allocation-failure case skips SPIM", "run_spim=true")
        return True
    return False


def assert_raw_compiler_success(case: TestCase, compiler_result: ExecutionResult) -> None:
    if compiler_result.timed_out:
        raise RunnerAssertionError(
            f"{case.id} [{case.pipeline_stage}] failed at compiler\n"
            f"input: {case.input_path}\n"
            f"expected: process completed before timeout\n"
            f"observed: timed out"
        )
    if compiler_result.exit_code != 0:
        raise RunnerAssertionError(
            f"{case.id} [{case.pipeline_stage}] failed at compiler\n"
            f"input: {case.input_path}\n"
            f"expected: exit code 0\n"
            f"observed: {compiler_result.exit_code}"
        )


def assert_raw_spim_stdout(
    case: TestCase,
    spim_result: ExecutionResult,
    expected_text: str,
) -> None:
    if spim_result.timed_out:
        raise RunnerAssertionError(
            f"{case.id} [{case.pipeline_stage}] failed at spim\n"
            f"input: {case.input_path}\n"
            f"expected: process completed before timeout\n"
            f"observed: timed out"
        )
    if spim_result.exit_code != 0:
        raise RunnerAssertionError(
            f"{case.id} [{case.pipeline_stage}] failed at spim\n"
            f"input: {case.input_path}\n"
            f"expected: exit code 0\n"
            f"observed: {spim_result.exit_code}"
        )
    assert_raw_text(case, "spim", expected_text, strip_spim_banner(spim_result.stdout))


def assert_raw_text(case: TestCase, stage: str, expected_text: str, observed_text: str) -> None:
    observed_text = observed_text.rstrip("\n")
    if observed_text != expected_text:
        raise RunnerAssertionError(
            f"{case.id} [{case.pipeline_stage}] failed at {stage}\n"
            f"input: {case.input_path}\n"
            f"expected: {expected_text!r}\n"
            f"observed: {observed_text!r}"
        )


def assert_stream(
    case: TestCase,
    stage: str,
    stream_name: str,
    actual: str,
    expected: dict[str, Any],
) -> None:
    if stream_name in expected and actual != expected[stream_name]:
        fail(case, f"{stage}.{stream_name}", expected[stream_name], actual)

    for needle in as_list(expected.get(f"{stream_name}_contains")):
        if needle not in actual:
            fail(case, f"{stage}.{stream_name}", f"text containing {needle!r}", actual)

    for needle in as_list(expected.get(f"{stream_name}_not_contains")):
        if needle in actual:
            fail(case, f"{stage}.{stream_name}", f"text without {needle!r}", actual)

    for pattern in as_list(expected.get(f"{stream_name}_regex")):
        if re.search(pattern, actual, flags=re.MULTILINE) is None:
            fail(case, f"{stage}.{stream_name}", f"text matching /{pattern}/", actual)


def assert_allowed_temp_registers(case: TestCase, text: str) -> None:
    used = set(re.findall(r"\$t\d+", text))
    disallowed = sorted(used - ALLOWED_TEMP_REGISTERS)
    if disallowed:
        fail(case, "generated.registers", "only $t0-$t9", ", ".join(disallowed))


def fail(case: TestCase, stage: str, expected: Any, observed: Any) -> None:
    raise RunnerAssertionError(
        f"{case.id} [{case.pipeline_stage}] failed at {stage}\n"
        f"input: {case.input_path}\n"
        f"expected: {expected!r}\n"
        f"observed: {observed!r}"
    )


def assert_official_text(
    case: OfficialCase,
    stage: str,
    expected_text: str,
    observed_text: str,
) -> None:
    if observed_text != expected_text:
        fail_official(case, stage, expected_text, observed_text)


def fail_official(case: OfficialCase, stage: str, expected: Any, observed: Any) -> None:
    raise RunnerAssertionError(
        f"official_{case.id} [official] failed at {stage}\n"
        f"input: {case.input_path}\n"
        f"expected: {expected!r}\n"
        f"observed: {observed!r}"
    )


def strip_spim_banner(stdout: str) -> str:
    lines = stdout.splitlines(keepends=True)
    kept: list[str] = []
    for line in lines:
        if line.rstrip("\n") in SPIM_BANNER_LINES:
            continue
        kept.append(line)
    return "".join(kept)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
