# MicroAgent-Edge

MicroAgent-Edge is an offline-first prototype for kernel-governed code-repair assistance on edge and embedded systems. The advisory model can inspect source and diagnostics and return a candidate patch. It cannot validate, execute, or apply that patch. Deterministic validators and the kernel retain those authorities.

## Architecture

- **agent/**: prompt construction, a lightweight Python AST/call-graph reader, and an injectable local inference interface. No network client or model runtime is included.
- **core/**: explicit FSM, deterministic Python AST checks, and bounded subprocess harness.
- **adapters/**: file-backed Python and C/C++ source targets behind an abstract environment contract.

The code is intentionally standard-library-only. A local Gemma runtime can be connected by injecting a function into GemmaAdvisoryAgent. Model loading and prompt-template compatibility are deployment-specific and are not simulated here.

## Install

Python 3.10 or newer is required. From a checkout, run python -m pip install . and python -m unittest discover -s tests -v. No packages need to be downloaded for the framework itself.

## Minimal example

    from core import ExecutionKernel, PythonProposalValidator, Sandbox
    kernel = ExecutionKernel([PythonProposalValidator()], Sandbox(timeout_seconds=2))
    result = kernel.process_proposal("print('candidate ran')")
    print(result.to_dict())

The kernel validates the whole proposed Python source before executing it in a temporary subprocess. The supplied harness applies a timeout and output bound, but a subprocess is not a security sandbox: it does not prevent filesystem, network, or OS access. Do not run untrusted proposals with this harness in production. Use OS/container isolation and least privilege. Static AST rules are defense in depth, not a proof of safety.

Adapters perform atomic source-file replacement only when explicitly called; they do not flash hardware or compile firmware. Kernel orchestration must be configured to call an adapter after validation and successful checks; this prototype does not provide hardware deployment authorization or rollback.

## Kaggle demo

Open notebooks/Gemma4_Edge_Agent_Demo.ipynb in Kaggle or Jupyter. It uses a deterministic local mock callback so the authority boundary can be demonstrated without downloading a model. Replace that callback with an offline Gemma inference function for a real model evaluation; report the model artifact, quantization, hardware, and measured resource use when doing so.

## Scope and limitations

This is a research prototype, not certified embedded safety software. C/C++ memory and array-bound analysis, device telemetry, compiler integration, patch diff application, rollback, and OS-level sandboxing require target-specific implementations. PythonProposalValidator checks syntax and a small deterministic denylist; it does not establish program correctness.

## License

Apache License 2.0. See LICENSE.
