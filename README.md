
## Kaggle competition runner

`runner.py` reads `tasks.jsonl` from `/kaggle/input/competitions/gemma-4-developer-agent/`, looks up matching files under `graphs/`, builds Python call-graph context, and sends structured prompts through `GemmaAdvisoryAgent`. Kernel validation and bounded subprocess checks gate any resulting patch. Each output row contains `id` (the task `instance_id`) and `prediction` (a single-file unified diff, or `NO_PATCH`), written to `/kaggle/working/submission.parquet`.

Provide an offline inference adapter exposing `generate(prompt: str) -> str` as JSON with string fields `proposed_patch` and `rationale`. Example invocation: `python runner.py --inference local_gemma_backend:generate`. The module and its model runtime must already be present locally; the runner does not download a model or call online APIs. `--data-dir`, `--output`, `--timeout`, and `--max-tasks` can override defaults. For Parquet serialization the runner uses PyArrow if it is already installed in the Kaggle image; it will fail clearly rather than install it.

The runner expects source text (or a source file mapping) in each task or its graph record; graph files alone that contain only AST metadata cannot provide replacement source. Its Python-only validator and subprocess harness are not a security boundary and must not be used to execute untrusted proposals on a host without OS-level isolation.
