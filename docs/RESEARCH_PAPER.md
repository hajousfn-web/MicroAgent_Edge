# MicroAgent-Edge: Kernel-Governed Advisory Repair for Edge Software

## Abstract

Edge and embedded development combines constrained compute with code whose failures may affect physical systems. This paper presents MicroAgent-Edge, a prototype that separates probabilistic code-repair advice from deterministic execution governance. A local language model may analyze source and diagnostics and propose a candidate; a kernel owns validation and any subsequent execution decision. The implementation supplies Python AST checks, a bounded subprocess harness, file-backed target adapters, and a reproducible notebook demonstration. It is an architectural prototype, not a certified safety mechanism.

## 1. Motivation and novelty

Local coding assistants commonly combine generation and action. That coupling complicates auditing when proposed code can reach a target. MicroAgent-Edge makes the authority boundary explicit: inference returns data only, while a separate kernel enforces a state machine and deterministic policy. The design is pluggable so a local inference backend and environment adapter can be replaced independently. The contribution is this verifiable separation and a small, dependency-free reference implementation, rather than a new language model or a claim of comprehensive static analysis.

## 2. System design

The advisory layer constructs a structured prompt and accepts a JSON-shaped candidate from an injected local inference function. A lightweight Python AST reader extracts function names, direct calls, and imports without importing or executing the analyzed program. No cloud endpoint or model package is required by the core distribution.

The authority layer tracks explicit states, rejects invalid transitions, runs configured deterministic validators, and only then invokes its subprocess harness. Validation checks parseability, source and AST size limits, and selected hazardous imports/calls. The harness uses a temporary directory, a wall-clock timeout, bounded captured output, isolated Python mode, and no shell. These are operational bounds, not an OS security boundary. A deployment handling untrusted code must add OS-level isolation, resource limits, restricted filesystem/network access, and least privilege.

Environment adapters define source reading, telemetry capture, and patch application. The included adapters atomically replace one configured local source file. They do not compile or flash firmware. Hardware approval, rollback, signed artifacts, and device-side verification remain deployment responsibilities.

## 3. Evaluation plan and verifiability

The included notebook demonstrates one accepted harmless proposal and one rejected candidate, and prints state/result records. Unit tests exercise deterministic validation, state transitions, and the advisory/kernel separation. This repository does not yet publish benchmark results. A verifiable follow-up evaluation should pin the model artifact and quantization, runtime/backend version, prompt, hardware, OS, energy and latency measurement method, and a fixed test corpus. Report acceptance/rejection confusion matrices, execution outcomes, resource use, and failures against a non-agent baseline. Do not infer safety from a small denylist.

## 4. Quality and significance

The implementation minimizes runtime dependencies, uses typed interfaces, and isolates model integration behind a callable protocol. The approach is relevant to edge systems because it permits offline inference and makes policy enforcement independent of model choice. The kernel/adapter contracts also support testing with deterministic fake backends before connecting hardware. The current prototype does not prove that a patch is correct, memory-safe, or appropriate for deployment; its checks are intentionally narrow.

## 5. Limitations and ethics

AST checks can be bypassed and do not reason about C/C++ memory bounds or full Python semantics. A subprocess with a timeout can still access host resources. Atomic file replacement is not an authorization system and does not provide rollback. A production system needs a hardened sandbox, target-specific validators, human approval for consequential changes, provenance logging, and safe recovery. No benchmark or hardware test is claimed by this draft.

## 6. Conclusion

MicroAgent-Edge offers a compact reference for separating offline AI advice from kernel-controlled validation and action. Its main value is an inspectable authority boundary and replaceable modules. Meaningful safety or performance claims require the reproducible target-specific evaluations described above.
