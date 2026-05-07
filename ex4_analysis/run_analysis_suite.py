#!/usr/bin/env python3
"""Run the well-defined Exercise 4 analysis fixtures against an Exercise 5 compiler."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

DEFAULT_TIMEOUT_SECONDS = 10.0
EXPECTED_TIMEOUT_SECONDS = 0.5
SPIM_BANNER_LINES = (
    "SPIM Version 8.0 of January 8, 2010",
    "Copyright 1990-2010, James R. Larus.",
    "All Rights Reserved.",
    "See the file README for a full copyright notice.",
    "Loaded: /usr/lib/spim/exceptions.s",
)


@dataclass(frozen=True)
class ExecutionResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


@dataclass(frozen=True)
class TestCase:
    id: str
    category: str
    mode: str
    input_path: Path
    expected_path: Path
    legacy_expected_path: Path
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


class RunnerAssertionError(AssertionError):
    """Assertion failure that carries enough context for the runner summary."""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--spim", default="spim")
    parser.add_argument(
        "--root",
        default=Path("tests/ex4_analysis"),
        type=Path,
        help="Root of the Ex4 analysis fixtures.",
    )
    parser.add_argument("--case")
    parser.add_argument(
        "--category",
        help=(
            "Run one category, e.g. official, additional-official, "
            "additional-official-unchanged, unofficial/ok, or unofficial/edge."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("compiler", "runtime"),
        help="Run only compiler-output checks or runtime/SPIM checks.",
    )
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--keep-temp", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        if not args.compiler.exists():
            raise FileNotFoundError(f"compiler not found: {args.compiler}")
        cases = load_cases(
            args.root,
            category=args.category,
            mode=args.mode,
            case_id=args.case,
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

    passed = len(cases) - len(failures)
    print(f"summary: {passed}/{len(cases)} passed")
    if failures:
        return 1
    return 0


def load_cases(
    root: Path,
    *,
    category: str | None = None,
    mode: str | None = None,
    case_id: str | None = None,
    timeout_seconds: float | None = None,
) -> list[TestCase]:
    if not root.is_dir():
        raise FileNotFoundError(f"missing suite root: {root}")

    cases = discover_cases(root, timeout_seconds or DEFAULT_TIMEOUT_SECONDS)
    if category:
        cases = [case for case in cases if case.category == category]
    if mode:
        cases = [case for case in cases if case.mode == mode]
    if case_id:
        cases = [case for case in cases if case.id == case_id]

    if case_id and not cases:
        raise ValueError(f"unknown test case: {case_id}")
    if category and not cases:
        raise ValueError(f"no test cases selected for category: {category}")
    if mode and not cases:
        raise ValueError(f"no test cases selected for mode: {mode}")
    if not cases:
        raise ValueError("no test cases found")

    ids = [case.id for case in cases]
    duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
    if duplicate_ids:
        raise ValueError(f"duplicate test case IDs: {', '.join(duplicate_ids)}")

    for case in cases:
        if not case.input_path.is_file():
            raise FileNotFoundError(f"missing input for {case.id}: {case.input_path}")
        if not case.expected_path.is_file():
            raise FileNotFoundError(
                f"missing expected output for {case.id}: {case.expected_path}"
            )
        if not case.legacy_expected_path.is_file():
            raise FileNotFoundError(
                f"missing legacy expected output for {case.id}: "
                f"{case.legacy_expected_path}"
            )
    return cases


def discover_cases(root: Path, timeout_seconds: float) -> list[TestCase]:
    cases: list[TestCase] = []
    expected_paths = sorted(root.rglob("expected_output/*_Expected_Output.txt"))
    expected_paths.extend(sorted(root.rglob("expected_output/*_Expected_Output.json")))
    for expected_path in expected_paths:
        if expected_path.name.endswith(".old"):
            continue
        rel_expected = expected_path.relative_to(root)
        stem = expected_stem(expected_path)
        category_parts = rel_expected.parts[:-2]
        category = "/".join(category_parts)
        input_path = root.joinpath(*category_parts, "tests", f"{stem}.txt")
        cases.append(
            make_case(
                category=category,
                case_id=case_id_from_parts((*category_parts, stem)),
                input_path=input_path,
                expected_path=expected_path,
                timeout_seconds=timeout_seconds,
            )
        )
    return cases


def make_case(
    *,
    category: str,
    case_id: str,
    input_path: Path,
    expected_path: Path,
    timeout_seconds: float,
) -> TestCase:
    legacy_expected_path = legacy_path_for(expected_path)
    legacy_text = legacy_expected_path.read_text(encoding="utf-8").strip()
    if legacy_text == "!OK":
        mode = "runtime"
    elif legacy_text.startswith("ERROR(") and legacy_text.endswith(")"):
        mode = "compiler"
    else:
        raise ValueError(
            f"non-well-defined legacy expected output in {legacy_expected_path}: "
            f"{legacy_text!r}"
        )

    return TestCase(
        id=case_id,
        category=category,
        mode=mode,
        input_path=input_path,
        expected_path=expected_path,
        legacy_expected_path=legacy_expected_path,
        timeout_seconds=timeout_seconds,
    )


def expected_stem(expected_path: Path) -> str:
    if expected_path.suffix == ".txt":
        return expected_path.name.removesuffix("_Expected_Output.txt")
    if expected_path.suffix == ".json":
        return expected_path.name.removesuffix("_Expected_Output.json")
    raise ValueError(f"unsupported expected-output file extension: {expected_path}")


def legacy_path_for(expected_path: Path) -> Path:
    if expected_path.suffix == ".json":
        legacy_name = expected_path.name.removesuffix(".json") + ".txt.old"
        return expected_path.with_name(legacy_name)
    return expected_path.with_name(expected_path.name + ".old")


def case_id_from_parts(parts: Sequence[str]) -> str:
    return "_".join(sanitize_part(part) for part in parts)


def sanitize_part(part: str) -> str:
    return part.replace("-", "_").replace("/", "_")


def run_case(case: TestCase, compiler: Path, spim: str, keep_temp: bool) -> None:
    expected = load_expected(case.expected_path)
    with isolated_work_dir(case, keep_temp) as work_dir:
        output_file = generated_output_path(work_dir, case)
        compiler_result = run_compiler(
            compiler=compiler,
            input_file=case.input_path,
            output_file=output_file,
            timeout_seconds=case.timeout_seconds,
        )
        if expected["kind"] == "structured":
            assert_process_observation(case, "compiler", compiler_result, expected["compiler"])
        else:
            assert_compiler_success(case, compiler_result)

        if not output_file.exists():
            fail(case, "generated", f"{output_file} exists", "missing")

        generated_text = output_file.read_text(encoding="utf-8")
        if expected["kind"] == "structured":
            assert_generated_output(case, output_file, expected["generated"])
            if "spim" in expected:
                spim_result = run_spim(
                    spim,
                    output_file,
                    timeout_seconds_for(case, expected["spim"]),
                )
                assert_process_observation(case, "spim", spim_result, expected["spim"])
            return

        expected_text = expected["raw_text"].rstrip("\n")
        if case.mode == "compiler":
            assert_raw_text(case, "generated", expected_text, generated_text)
            return

        generated_summary = generated_text.strip()
        if (
            generated_summary.startswith("ERROR")
            or generated_summary == "Register Allocation Failed"
            or generated_summary == expected_text
        ):
            fail(case, "generated", "runnable MIPS assembly", generated_summary)

        spim_result = run_spim(spim, output_file, case.timeout_seconds)
        assert_spim_stdout(case, spim_result, expected_text)


def load_expected(expected_path: Path) -> dict[str, Any]:
    text = expected_path.read_text(encoding="utf-8")
    if expected_path.suffix == ".json":
        payload = json.loads(text)
        return {
            "kind": "structured",
            "compiler": payload.get("compiler", {}),
            "generated": payload.get("generated", {}),
            **({"spim": payload["spim"]} if "spim" in payload else {}),
        }
    if expected_path.suffix == ".txt":
        return {"kind": "raw", "raw_text": text}
    raise ValueError(f"unsupported expected-output file extension: {expected_path}")


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


def assert_compiler_success(case: TestCase, result: ExecutionResult) -> None:
    if result.timed_out:
        fail(case, "compiler", "process completed before timeout", "timed out")
    if result.exit_code != 0:
        raise RunnerAssertionError(
            f"{case.id} [{case.category}/{case.mode}] failed at compiler\n"
            f"input: {case.input_path}\n"
            f"expected: exit code 0\n"
            f"observed: {result.exit_code}\n"
            f"stdout: {result.stdout!r}\n"
            f"stderr: {result.stderr!r}"
        )


def assert_process_observation(
    case: TestCase,
    stage: str,
    result: ExecutionResult,
    expected: dict[str, Any],
) -> None:
    if expected.get("timed_out") is True:
        if not result.timed_out:
            fail(case, stage, "timed out", f"exit code {result.exit_code}")
        return

    if result.timed_out:
        fail(case, stage, "process completed before timeout", "timed out")
    if "exit_code" in expected and result.exit_code != expected["exit_code"]:
        fail(case, stage, f"exit code {expected['exit_code']}", result.exit_code)
    assert_stream(case, stage, "stdout", result.stdout, expected)
    assert_stream(case, stage, "stderr", result.stderr, expected)


def timeout_seconds_for(case: TestCase, expected: dict[str, Any]) -> float:
    if expected.get("timed_out") is True:
        return EXPECTED_TIMEOUT_SECONDS
    return case.timeout_seconds


def assert_generated_output(
    case: TestCase,
    generated_file: Path,
    expected: dict[str, Any],
) -> None:
    if not expected:
        return

    if expected.get("exists") and not generated_file.exists():
        fail(case, "generated", f"{generated_file} exists", "missing")

    text = generated_file.read_text(encoding="utf-8") if generated_file.exists() else ""

    if expected.get("non_empty") and not text.strip():
        fail(case, "generated", "non-empty generated output", "empty output")

    if "exact_text" in expected and text != expected["exact_text"]:
        fail(case, "generated", expected["exact_text"], text)

    for needle in as_list(expected.get("contains")):
        if needle not in text:
            fail(case, "generated", f"output containing {needle!r}", text)

    for needle in as_list(expected.get("not_contains")):
        if needle in text:
            fail(case, "generated", f"output without {needle!r}", text)


def assert_spim_stdout(
    case: TestCase,
    result: ExecutionResult,
    expected_text: str,
) -> None:
    if result.timed_out:
        fail(case, "spim", "process completed before timeout", "timed out")
    if result.exit_code != 0:
        raise RunnerAssertionError(
            f"{case.id} [{case.category}/{case.mode}] failed at spim\n"
            f"input: {case.input_path}\n"
            f"expected: exit code 0\n"
            f"observed: {result.exit_code}\n"
            f"stdout: {result.stdout!r}\n"
            f"stderr: {result.stderr!r}"
        )
    assert_raw_text(case, "spim", expected_text, strip_spim_banner(result.stdout))


def assert_raw_text(
    case: TestCase,
    stage: str,
    expected_text: str,
    observed_text: str,
) -> None:
    observed_text = observed_text.rstrip("\n")
    if observed_text != expected_text:
        raise RunnerAssertionError(
            f"{case.id} [{case.category}/{case.mode}] failed at {stage}\n"
            f"input: {case.input_path}\n"
            f"expected: {expected_text!r}\n"
            f"observed: {observed_text!r}"
        )


def strip_spim_banner(stdout: str) -> str:
    lines = stdout.splitlines(keepends=True)
    kept: list[str] = []
    for line in lines:
        if line.rstrip("\n") in SPIM_BANNER_LINES:
            continue
        kept.append(line)
    return "".join(kept)


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


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def fail(case: TestCase, stage: str, expected: object, observed: object) -> None:
    raise RunnerAssertionError(
        f"{case.id} [{case.category}/{case.mode}] failed at {stage}\n"
        f"input: {case.input_path}\n"
        f"expected: {expected!r}\n"
        f"observed: {observed!r}"
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
