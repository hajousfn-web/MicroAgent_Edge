# MicroAgent-Edge

MicroAgent-Edge is an offline-first prototype for kernel-governed code-repair assistance on edge and embedded systems. The advisory model can inspect source and diagnostics and return a candidate patch. It cannot validate, execute, or apply that patch. Deterministic validators and the kernel retain those authorities.

## Architecture

- **agent/**: prompt construction, a lightweight Python AST/call-graph reader, and an injectable local inference interface. No network client or model runtime is included.
- **core/**: explicit FSM, deterministic Python AST checks, and bounded subprocess harness.
- **adapters/**: file-backed Python and C/C++ source targets behind an abstract environment contract.

The code is intentionally standard-library-only. A local Gemma runtime can be connected by injecting a function into `GemmaAdvisoryAgent`. Model loading and prompt-template compatibility are deployment-specific and are not simulated here.

## Install

Python 3.10 or newer is required. From a checkout, run `python -m pip install .` and `python -m unittest discover -s tests -v`. No packages need to be downloaded for the core framework.

## Minimal example

```python
from core import ExecutionKernel, PythonProposalValidator, Sandbox

kernel = ExecutionKernel([PythonProposalValidator()], Sandbox(timeout_seconds=2))
result = kernel.process_proposal("print('candidate ran')")
print(result.to_dict())
```

The kernel validates proposed Python source before executing it in a temporary subprocess. The supplied harness applies a timeout and output bound, but a subprocess is not a security sandbox: it does not prevent filesystem, network, or OS access. Do not run untrusted proposals with this harness in production. Use OS/container isolation and least privilege. Static AST rules are defense in depth, not a proof of safety.

Adapters perform atomic source-file replacement only when explicitly called; they do not flash hardware or compile firmware. Kernel orchestration can call an adapter after validation and successful checks; this prototype does not provide hardware deployment authorization or rollback.

## Kaggle demo

Open `notebooks/Gemma4_Edge_Agent_Demo.ipynb` in Kaggle or Jupyter. It uses a deterministic local mock callback so the authority boundary can be demonstrated without downloading a model. Replace that callback with an offline Gemma inference function for a real model evaluation; report the model artifact, quantization, hardware, and measured resource use when doing so.

## Kaggle competition runner

`runner.py` reads `tasks.jsonl` from `/kaggle/input/competitions/gemma-4-developer-agent/`, looks up matching files under `graphs/`, builds Python call-graph context, and sends structured prompts through `GemmaAdvisoryAgent`. Kernel validation and bounded subprocess checks gate any resulting patch. Each output row contains `id` (the task `instance_id`) and `prediction` (a single-file unified diff, or `NO_PATCH`), written to `/kaggle/working/submission.parquet`.

Provide an offline inference adapter exposing `generate(prompt: str) -> str` that returns JSON with string fields `proposed_patch` and `rationale`. Example: `python runner.py --inference local_gemma_backend:generate`. The module and its model runtime must already be present locally; the runner does not download a model or call online APIs. `--data-dir`, `--output`, `--timeout`, and `--max-tasks` can override defaults. `--max-retries` defaults to 2, allowing the initial proposal plus up to two correction attempts. The subprocess timeout defaults to 0.5 seconds and applies per proposal; it does not bound Gemma inference time. Parquet serialization uses PyArrow if it is already installed in the Kaggle image; the runner fails clearly rather than downloading it.

The runner expects source text (or a source file mapping) in each task or its graph record; graph files containing only AST metadata cannot provide replacement source. Its Python-only validator and subprocess harness are not a security boundary and must not execute untrusted proposals on a host without OS-level isolation.

## Scope and limitations

This is a research prototype, not certified embedded safety software. C/C++ memory and array-bound analysis, device telemetry, compiler integration, multi-file patch generation, rollback, and OS-level sandboxing require target-specific implementations. `PythonProposalValidator` checks syntax and a small deterministic denylist; it does not establish program correctness.

## License

Apache License 2.0. See [LICENSE](LICENSE).
