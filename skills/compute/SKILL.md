---
name: compute
description: >-
  Run a Python function on a fresh cloud GPU with Compute (compute.cx) via the
  CLI or `compute mcp`. Use when installing Compute, signing in, adding prepaid
  credit, dry-running a payload, submitting a GPU job, following logs, reading a
  receipt, canceling a run, or configuring the Compute MCP server. Runs spend
  prepaid credit; --dry-run and compute_dry_run create no machine.
---

# Compute

Canonical skill URL: `https://compute.cx/SKILL.md`

Also published at `https://compute.cx/.well-known/skills/compute/SKILL.md`

Compute uploads a Python function, provisions a **new** GPU machine for that run, streams output, returns JSON, then terminates the machine by default. To reuse a GPU across sequential jobs, explicitly create a held machine; it bills while up, including idle time. You do not log into the machine or pick a region.

Human manual: `https://docs.compute.cx`

MCP (stdio): `compute mcp` after the CLI is installed and signed in. MCP (hosted, Streamable HTTP): `https://mcp.compute.cx/mcp` — no local install; use when the caller cannot spawn a local process.

## Rules

- GPU runs spend **prepaid credit**. Confirm the quote. `--yes` and MCP `compute_run` with `confirm_spend=true` skip the interactive confirmation and still spend.
- A hosted quote with `fallback=true` needs separate approval: set top-level `accept_selector_fallback=true` only after the user accepts that warning. `confirm_spend` does not imply fallback approval.
- `--dry-run` creates no machine. Hosted MCP `compute_dry_run` stores the inline source as a payload and creates an expiring quote, but starts no run or machine and spends no execution credit.
- `compute run … --quote-only` (CLI 0.1.20+) uploads, quotes, prints the priced preflight, and exits 0 without creating a run or a hold, so a caller without a TTY can read the price before rerunning with `--yes`. Without `--yes` on a non-interactive terminal the CLI now prints the same preflight before refusing (exit 2).
- Do not invent files. The first example below is complete; write it to disk before `compute run` or local MCP `compute_dry_run`. Hosted MCP receives those files inline.
- Do not paste `COMPUTE_API_KEY`, `~/.compute/config.toml`, Checkout session ids, or secret values into chat logs.
- Do not use `pip install compute`. v0.1 install is `curl|sh` only.
- Live SKUs come from `compute gpu list`, MCP `compute_list_gpus`, and https://compute.cx/gpus. Do not pass a name that list does not show. `--gpu` may be a SKU, `PROVIDER/SKU`, or a policy: `auto`, `fast`, `cheap` (`fastest` / `cheapest` also accepted). Policies pick from the live catalog — confirm the quoted SKU and rate before spend. Public reserved lead is **H100-SXM** (`H100` and `H100-80GB` are aliases). Reserved RunPod also lists **A100-PCIe-80GB**, **A100-SXM-80GB**, **H100-PCIe**, and **H200** — pass `--provider runpod` or `runpod/<SKU>`. **MI300X** is AMD. Vast.ai spot SKUs include **RTX-3090**, **RTX-4090**, **RTX-5090**, **L4**, **A100-40GB**, **A100-80GB**, and **H100-SXM** — pass `--provider vastai` or `vastai/<SKU>`. Bare `A100-80GB` is Vast interruptible, not reserved RunPod. Spot capacity can be reclaimed; Compute then ends the run and tears the machine down. Do not invent a $/hr number; use `compute gpu list` or `compute_list_gpus`.
- There is no per-account cap on concurrent runs or machines. You can also keep several model deployments and Tinker sessions live at once. Spend and provider capacity can refuse a create even with a positive balance. There is no hourly create-rate cap.

## Install and sign in

macOS or Linux, Python 3.10–3.14:

```bash
curl -fsSL https://compute.cx/install.sh | sh
compute --version
compute setup
compute doctor --json
```

`compute setup` opens a browser on compute.cx. On success it writes `~/.compute/config.toml` (mode `0600`).

CI uses a revocable dashboard key instead of device login:

```bash
export COMPUTE_API_KEY='ck_live_…'
```

## MCP server

Two ways to reach Compute over MCP: a local stdio process for hosts that can spawn one, and a hosted Streamable HTTP endpoint for hosts that cannot.

### Local (stdio)

`compute mcp` is a stdio Model Context Protocol server. The host (Cursor, Claude Code, Codex, and similar) must spawn it. Do not run it in an interactive shell.

Cursor `mcp.json` (project or `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "compute": {
      "command": "compute",
      "args": ["mcp"]
    }
  }
}
```

The process uses `COMPUTE_API_KEY` or `~/.compute/config.toml`. After `compute setup`, no extra env is required.

Prefer `compute_dry_run` then `compute_run` (with `confirm_spend=true`) when the working tree has the entrypoint file: the local server reads it from disk to build the upload. (The hosted server below takes the source inline instead.) A cold `compute_run` requires `confirm_spend=true`; a job on a ready held machine does not, because the machine's owner run already holds credit and bills its uptime.

Full tool set (37): the 36 hosted tools listed below plus `compute_doctor` (local stdio only — it exists because the CLI runs on the user's own machine and can inspect its own install/auth state; the hosted server cannot). `compute_dry_run`/`compute_run` read `entrypoint`/`project_root` from the local filesystem instead of taking `files` inline, and take no `pip`/`secrets`/`image` argument: declare those on the source file's `@app.function(...)` decorator.

One-click Cursor deeplink (after the CLI is on PATH):

`cursor://anysphere.cursor-deeplink/mcp/install?name=compute&config=eyJjb21tYW5kIjoiY29tcHV0ZSIsImFyZ3MiOlsibWNwIl19`

Portable Agent Plugin (skill + MCP install): the public docs repo `theoriclabs/docs.compute.cx` (`plugin.json`, `mcp.json`, `skills/compute/SKILL.md`). Submit/install from [Cursor Marketplace](https://cursor.com/marketplace) or a team marketplace that imports that repo.

### Hosted (Streamable HTTP + OAuth)

`https://mcp.compute.cx/mcp` — for cloud/hosted agents (Claude.ai- or ChatGPT-style connectors, background agents) that cannot spawn a local process. No CLI install, no `COMPUTE_API_KEY`.

Auth is Clerk OAuth 2.1 + PKCE with Dynamic Client Registration. Discover it from `https://mcp.compute.cx/.well-known/oauth-protected-resource/mcp`; a request without a valid token gets `401` with a `WWW-Authenticate` header pointing at that same discovery document. The authorization server (`https://clerk.compute.cx`) publishes a `registration_endpoint`, so an MCP host can self-register a client and complete the browser consent without anything pre-registered. The consent signs in the Compute account whose prepaid credit the runs will spend.

Full tool set (36): `compute_whoami`, `compute_credits`, `compute_credits_add`, `compute_usage`, `compute_list_gpus`, `compute_dry_run`, `compute_run`, `compute_list_runs`, `compute_get_run`, `compute_inspect_run`, `compute_get_logs`, `compute_get_result`, `compute_get_receipt`, `compute_cancel_run`, `compute_list_machines`, `compute_get_machine`, `compute_create_machine`, `compute_delete_machine`, `compute_inspect_model`, `compute_plan_model_deployment`, `compute_create_model_deployment`, `compute_list_model_deployments`, `compute_get_model_deployment`, `compute_stop_model_deployment`, `compute_reveal_model_endpoint_token`, `compute_rotate_model_endpoint_token`, `compute_list_secrets`, `compute_set_secret`, `compute_delete_secret`, `compute_list_artifacts`, `compute_get_artifact`, `compute_report_issue`, `compute_get_report`, `compute_create_budget`, `compute_get_budget`, `compute_update_budget`. Hosted `compute_dry_run` takes the Python source **inline** instead of reading disk: `entrypoint` (`file.py::function`) plus `files`, an array of `{path, content}` holding the entrypoint, every local module it imports, and any non-Python files the decorator declares in `include=[...]` (at most 64 files, 2 MiB of UTF-8 text total). Third-party packages go in `pip`, not in `files`. It stores the payload, creates no run or machine, and returns the quote plus a versioned `prepared_run`. Hosted `compute_run` accepts that `prepared_run` unchanged plus `confirm_spend=true`; it launches against the same quote without repacking or requoting and spends prepaid credit. If that quote reports `fallback=true`, pass the separate top-level `accept_selector_fallback=true` only after explicit user approval; do not put it inside `prepared_run`. With `machine_id`, `compute_dry_run` binds the `prepared_run` to a held machine instead of a quote, and `compute_run` launches it without `confirm_spend` (see [Held machines](#held-machines)).

## Deploy a Hugging Face model

The default CLI path inspects the Hub repository, pins the revision, accepts the server's recommended runtime and cheapest compatible suggested machine, and creates a private endpoint:

```bash
compute deploy owner/model
compute deployments status <deployment_id>
compute deployments reveal-token <deployment_id>
compute deployments stop <deployment_id>
```

Use `--revision`, `--file`, `--hf-secret`, `--configuration`, `--provider`, `--sku`, or `--cloud-type` only when the user wants to override the recommendation. A best-effort plan that bills from allocation stops before creation and requires a second call with `--accept-startup-risk` after the user reviews the selected machine and price.

MCP follows the same state machine: `compute_inspect_model` → `compute_plan_model_deployment` → `compute_create_model_deployment`. Reuse the same `idempotency_key` after an uncertain create response. Then use `compute_get_model_deployment`, reveal or rotate the endpoint token only when explicitly requested, and call `compute_stop_model_deployment` for teardown. Never place a Hugging Face token in a model URL or tool output; save it with `compute_set_secret` and pass only `hf_secret_name`.

## Credit

Minimum Checkout is **$10**. Balance updates after the payment webhook, not when the Checkout tab opens.

```bash
compute credits add 10
compute credits
```

MCP: `compute_credits_add` (returns `checkout_url`) and `compute_credits`.

A run is refused if the hold would exceed remaining credit or a spend cap. Billing is started minutes while the machine exists, plus a flat **7.5%** platform fee. Failed boots that never start the machine are $0. `--timeout` is a kill limit (default 600, API maximum 86400), not expected runtime. Confirm the quote and `compute runs receipt <run_id>` or MCP `compute_get_receipt`.

## First example

Save this file as `simple_mlp.py` in the working directory (source also in [First run](https://docs.compute.cx/get-started/first-run)):

```python
import compute

app = compute.App("simple-mlp")
image = compute.Image.cuda_pytorch()


@app.function(gpu="H100-80GB", image=image, timeout=600)
def train(steps: int = 40, hidden: int = 32, seed: int = 0) -> dict:
    import torch
    import torch.nn as nn

    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = nn.Sequential(
        nn.Linear(16, hidden),
        nn.ReLU(),
        nn.Linear(hidden, 2),
    ).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()
    x = torch.randn(256, 16, device=device)
    y = (x.sum(dim=1) > 0).long()
    last = None
    for _ in range(steps):
        opt.zero_grad()
        last = loss_fn(model(x), y)
        last.backward()
        opt.step()
    return {
        "ok": True,
        "compat": "mlp",
        "device": str(device),
        "cuda": bool(torch.cuda.is_available()),
        "steps": steps,
        "loss": float(last.detach()),
        "torch": torch.__version__,
    }
```

`gpu="H100-80GB"` is the same SKU as `H100-SXM`. Arguments and the return value must be JSON. Put GPU-only imports **inside** the function.

## Non-Python files and programs

The payload is the entrypoint plus the local Python modules it imports. Anything else (data, configs, a Lean/Lake, C or Rust project the function builds and runs) ships only when the decorator names it (CLI 0.1.21+):

```python
@app.function(gpu="vastai/A100-80GB", image=compute.Image.cuda_pytorch(), include=["lakefile.lean", "lean-toolchain", "Main.lean", "PtxCheck"])
def check() -> int:
    import subprocess
    return subprocess.run(["lake", "exe", "ptxcheck"]).returncode
```

- Paths are relative to the project root (the entrypoint's directory, or `--project-root`). A directory is walked recursively; inside it, names starting with `.` (`.git`, `.lake`, `.venv`) and `__pycache__` are skipped. Name a dot file explicitly to ship it. `include=["."]` ships the whole project directory under those rules.
- Files land at the same relative paths in the run's working directory. Symlinks are refused, and executable bits are not kept (run scripts through their interpreter or `chmod` them first). Limits: 32 MiB compressed, 64 MiB uncompressed, 10,000 files.
- `--dry-run` lists every file that will ship. Hosted MCP sends included files inline in `files` as UTF-8 text, and the decorator must still declare them.
- The entrypoint is still a Python function, which runs the program with `subprocess`. Toolchains are not preinstalled: the function installs them at run time, for example `ptxas` from the `nvidia-cuda-nvcc-cu12==12.4.131` pip package (at `site-packages/nvidia/cuda_nvcc/bin/ptxas`, not on `PATH`) or Lean from elan (set `ELAN_HOME` under the working directory, since `$HOME` may be read-only).

## Dry-run, then pay

See what would ship. This must not create a machine:

```bash
compute run simple_mlp.py::train --gpu H100-SXM --dry-run
```

Local MCP: `compute_dry_run` with `entrypoint=simple_mlp.py::train` and `gpu=H100-SXM`; it reads the working tree. Hosted MCP also needs the source closure in `files` and returns the quote-bound `prepared_run` used for launch.

NVIDIA image: `compute.Image.cuda_pytorch()`. AMD / MI300X: `compute.Image.rocm_pytorch()`. Mixing them is a failed run. Both curated images install a pinned torch at run start (`torch==2.5.1+cu124` plus `numpy` on CUDA, `torch==2.7.1+rocm6.3` plus `numpy` on ROCm) unless the image's `pip_install(...)` names a `torch*` package, in which case your pin wins. Expect the install to add a minute or more of boot time.

When the user has credit and wants a real run:

```bash
compute gpu list
compute run simple_mlp.py::train --gpu H100-SXM --wait --yes --args '{"steps": 40, "seed": 20260814}'
compute run simple_mlp.py::train --provider vastai --gpu RTX-4090 --wait --yes
```

Local MCP: `compute_list_gpus`, then `compute_run` with `confirm_spend=true` and optional `wait=true`. Hosted MCP: pass the `prepared_run` from `compute_dry_run` unchanged to `compute_run` with `confirm_spend=true`, add top-level `accept_selector_fallback=true` only when separately approved for a fallback quote, then poll `compute_get_run` until terminal.

- CLI `--wait` follows live output until a terminal state. Local MCP `wait=true` blocks until terminal and returns one captured response; it does not publish an MCP event stream.
- Without waiting, the CLI or local MCP returns after creation. Follow with CLI `compute logs <run_id> -f`, or poll `compute_get_run` over MCP.
- Hosted `compute_get_logs` is a bounded, non-streaming snapshot of at most the final 32,000 available characters. After a terminal state call `compute_get_receipt`; call `compute_get_result` only after success when a result is available.
- `--yes` / `confirm_spend=true` is for non-interactive execution. Tell the user it bypasses the price prompt and will spend credit.
- If the terminal is interactive and the user did not opt out, omit `--yes` so they can confirm spend.

## Held machines

For short iterations (a kernel, a training step), hold one GPU and run jobs on it by id instead of paying a cold boot for every run (CLI 0.1.22+):

```bash
compute machines create --gpu runpod/H100-SXM   # prints m_...; waits until ready
compute run simple_mlp.py::train --machine m_... --wait
compute machines rm m_...
```

MCP:

1. `compute_create_machine` with `gpu_sku` and `confirm_spend=true`, only after the user accepts the hourly rate (`compute_list_gpus`) and the limits. It returns at once with `state: requested`.
2. Poll `compute_get_machine` until `state` is `ready`.
3. Local: `compute_run` with `entrypoint` and `machine_id`. Hosted: `compute_dry_run` with `files` and `machine_id`, then `compute_run` with that `prepared_run` unchanged. Neither needs `confirm_spend`, and neither quotes. Call `compute_dry_run` again for each new hosted job.
4. `compute_delete_machine` when done.

- The machine holds credit for its whole lifetime and bills every minute it is up, idle minutes included. Jobs on it bill nothing themselves. It stops after `idle_timeout_seconds` with no job (default 600), at `max_lifetime_seconds` after ready (default 28800), or on delete.
- One job at a time: a second one gets `machine_busy`. The image is fixed at boot (default `compute-cuda`, which is `Image.cuda_pytorch()`), so a job with another image gets `image_mismatch`. A stopped machine gives `machine_unavailable`; the MCP run tools answer `machine_not_ready` while it boots.

## Inspect and tear down

```bash
compute runs list
compute runs status <run_id>
compute runs result <run_id>
compute runs receipt <run_id>
compute logs <run_id> -f
compute artifacts list <run_id>
compute artifacts get <run_id> <artifact_id> <version> --out ./weights
compute cancel <run_id>
compute machines
```

MCP: `compute_list_runs`, `compute_get_run`, `compute_inspect_run`, `compute_get_result`, `compute_get_receipt`, `compute_get_logs`, `compute_list_artifacts`, `compute_get_artifact`, `compute_cancel_run`, `compute_list_machines`.

Terminal execution (`status` in `succeeded`/`failed`/`boot_failed`/`cancelled`/`timeout`/`killed_low_balance`/`lost`) does not by itself prove final settlement — amounts on `compute_get_receipt` stay provisional until then. Call `compute_inspect_run` (bounded waiting, resumable by cursor) and follow its `next_action` until `settlement.status` is `final`, or until it reports an explicit evidence gap. Only then call `compute_get_result` (only meaningful after `succeeded`) or `compute_get_artifact` for output bytes.

`compute_list_artifacts` returns metadata only, never bytes. `compute_get_artifact` verifies and returns the bytes themselves: small text inlines, everything else up to 64 MiB comes back as an MCP host resource, and anything larger stays metadata-only with a pointer to `compute artifacts get`. The CLI's `compute artifacts get <run_id> <artifact_id> <version> --out <dir>` remains the way to write files straight to disk.

Files the job writes under `$COMPUTE_ARTIFACT_DIR` with a `.compute-artifact.json` marker are uploaded to object storage before teardown. After the machine is gone, `compute artifacts get` is how the user retrieves them.

`compute machines` / `compute_list_machines` should be empty after teardown, apart from held machines you created. That is expected.

## If create is refused

Keep the request id from the error body plus the run id if one exists. The CLI can run `compute doctor --json`; `compute_doctor` exists only in local stdio MCP. Use `compute_report_issue` for a structured report. It may return an immediate answer; if its status remains `open`, keep the report id and call `compute_get_report` later. See [Support](https://docs.compute.cx/support).
