# Compiler Exercise Test Suites

This repository contains Python runners and fixture suites for testing a compiler submission across exercises 1 through 5. The normal entry point is `run_all_suites.py`, which builds the submitted Exercise 5 compiler and then runs each phase-specific suite against the generated `COMPILER` jar.

## Prerequisites

- Python 3.9 or newer.
- Java, available as `java`.
- `make`.
- SPIM, available as `spim`, for runtime tests that execute generated MIPS.
- Exactly one numeric submission zip at the repository root, for example `123456789.zip`.

The submission zip must extract an `ex5/` project containing a `Makefile`. The top-level runner runs `make` inside `ex5/` and expects the build to produce `ex5/COMPILER`.

## Quick Start

From the repository root:

```sh
python3 run_all_suites.py
```

The runner will:

1. Find the single numeric `*.zip` submission in the repository root.
2. Extract it into the repository.
3. Run `make` in `ex5/`.
4. Run the selected phase suites with `ex5/COMPILER`.
5. Print per-phase summaries and a combined summary.

Exit codes:

- `0`: all selected phases passed.
- `1`: at least one selected phase had test failures.
- `2`: setup or usage error, such as no submission zip, multiple numeric zips, missing runner, missing compiler, or bad suite root.

## Common Commands

Run all phases:

```sh
python3 run_all_suites.py
```

Run one phase:

```sh
python3 run_all_suites.py --phase ex5
```

Run several phases:

```sh
python3 run_all_suites.py --phase ex1 --phase ex2 --phase ex3
```

Use a non-default SPIM executable:

```sh
python3 run_all_suites.py --spim /path/to/spim
```

Override the per-test timeout used by phase runners:

```sh
python3 run_all_suites.py --timeout 20
```

Keep temporary work directories for debugging:

```sh
python3 run_all_suites.py --keep-temp
```

## Phase Runners

Each phase can also be run directly after `ex5/COMPILER` exists. Direct runs are useful when debugging a single category or case.

Exercise 1 lexical:

```sh
python3 ex1_lexical/run_lexical_suite.py \
  --compiler ex5/COMPILER \
  --root ex1_lexical
```

Exercise 2 parsing:

```sh
python3 ex2_parsing/run_parsing_suite.py \
  --compiler ex5/COMPILER \
  --root ex2_parsing
```

Exercise 3 semantic:

```sh
python3 ex3_semantic/run_semantic_suite.py \
  --compiler ex5/COMPILER \
  --root ex3_semantic
```

Exercise 4 analysis:

```sh
python3 ex4_analysis/run_analysis_suite.py \
  --compiler ex5/COMPILER \
  --root ex4_analysis
```

Exercise 5 code generation:

```sh
python3 ex5_codegen/run_codegen_suite.py \
  --compiler ex5/COMPILER \
  --inputs ex5_codegen/unofficial/inputs \
  --expected ex5_codegen/unofficial/expected \
  --coverage-index ex5_codegen/coverage-index.csv
```

Use `--help` on any runner to see all filters. Most runners support:

- `--case CASE_ID` to run one test case.
- `--category CATEGORY` to run one fixture group.
- `--mode compiler` or `--mode runtime` where applicable.
- `--timeout SECONDS`.
- `--keep-temp`.

## Architecture

The repository is organized as a thin orchestration layer plus independent phase suites.

`run_all_suites.py` is the orchestrator. It owns submission discovery, unzip, build, phase selection, and the combined summary. It does not implement test assertions itself. Instead, it defines the five phases and delegates to the existing phase runner for each one.

The phase directories contain the fixtures and assertion logic for one compiler milestone:

- `ex1_lexical/`: lexical fixtures. Tests check tokenization behavior and lexical error reporting.
- `ex2_parsing/`: parsing fixtures. Tests include lexer compatibility, parser coverage, precedence, syntax errors, edge cases, AST structure, and official tests.
- `ex3_semantic/`: semantic fixtures. Tests include compiler-error cases and valid-program runtime cases grouped by type system, arrays, classes, assignments, functions, control flow, scope, library calls, and larger programs.
- `ex4_analysis/`: well-defined analysis fixtures. Tests compare compiler output and, for valid programs, run generated MIPS through SPIM. The runner also accepts the legacy `well_defined_behavior` root path used by the top-level runner and resolves it to the current fixture layout.
- `ex5_codegen/`: code-generation fixtures. Tests cover IR structure, register allocation behavior, MIPS output, runtime checks, and official Exercise 5 programs.

## Fixture Model

The runners follow a consistent pattern:

1. Discover input files and expected-output files under the phase root.
2. Create an isolated temporary directory for generated outputs.
3. Invoke the compiler as:

   ```sh
   java -jar ex5/COMPILER input-file output-file
   ```

4. Check compiler exit code, generated output, or expected error text.
5. For runtime cases, execute the generated MIPS with SPIM and compare stdout after removing the standard SPIM banner.

Expected outputs may be plain text or structured JSON depending on the suite. Some semantic and analysis fixtures keep legacy expected-output files with a `.old` suffix; these are used by the runners to classify cases as compiler-error checks or runtime checks.

## Debugging Failed Cases

Start with a focused rerun:

```sh
python3 run_all_suites.py --phase ex4 --keep-temp
```

Then copy the failing case ID from the output and run the phase runner directly:

```sh
python3 ex4_analysis/run_analysis_suite.py \
  --compiler ex5/COMPILER \
  --root ex4_analysis \
  --case failing_case_id \
  --keep-temp
```

When `--keep-temp` is set, the runner prints the temporary directory path for each case, including the generated MIPS file. That directory is useful for comparing compiler output, running SPIM manually, or inspecting intermediate artifacts.
