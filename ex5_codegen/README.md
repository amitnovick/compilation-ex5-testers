# Exercise 5 Code Generation Test Runner

This directory contains a Python subprocess-based runner for the Exercise 5
L-to-MIPS compiler pipeline. It invokes the compiled `COMPILER`, captures
compiler stdout, stderr, and exit code, then runs generated MIPS text files with
SPIM 8.0 when a case requires runtime execution.

## Scope

Only Exercise 5 behavior belongs here:

- IR generation for code generation behavior
- Liveness analysis and simplification-based register allocation
- The 10-register allocation limit and `Register Allocation Failed`
- MIPS assembly translation
- Saturation arithmetic, left-to-right evaluation, and exact Exercise 5 runtime
  error messages

Do not add inputs whose purpose is lexical validation, syntax validation,
semantic validation, or any Exercise 1 through Exercise 4 rule.

## Running

```bash
python3 tests/ex5_codegen/run_codegen_suite.py \
  --compiler ./ex5/COMPILER \
  --spim spim
```

Use `--category ir`, `--category allocation`, `--category mips`, or
`--category runtime` to run one Exercise 5 area. Use `--case CASE_ID` to run one
descriptive case.

Full runs also execute the official self-check tests under `official-tests/`
using the same compile, optional SPIM, and exact expected-output comparison
contract as `official-test-runner.py`. Use `--skip-official` to run only the
unofficial coverage-index suite.

## Input Authoring

Each case has:

- An immutable `.l` input under `unofficial/inputs/<category>/`
- A matching expectation under `unofficial/expected/<category>/`
- One or more rows in `coverage-index.csv`
- A descriptive case entry in `run_codegen_suite.py`

Use `.json` for structured compiler/generated-output assertions. Use `.txt`
for exact raw compiler output, SPIM output, or runtime crash messages.

Keep Arrange data in input and expected files. The Act step is always the
runner invoking `COMPILER <input> <output>` and, when needed, SPIM 8.0. The
Assert step belongs in expected observations and assertion helpers.

The coverage index is the source of truth for comprehensive Exercise 5 coverage.
It must include concrete behavior-family topics for IR structure, liveness and
allocation, successful MIPS execution, saturation arithmetic, left-to-right
evaluation, and exact runtime crashes. Broad rows such as `MIPS translation`
are not enough on their own.

Expected SPIM output files should contain only program behavior or exact runtime
messages. The runner strips the SPIM startup banner before comparing stdout.

Generated compiler output and captured streams must stay in per-case temporary
directories. Use `--keep-temp` only for debugging failed runs.
