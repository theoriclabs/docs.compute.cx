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

Compute uploads a Python function, provisions a **new** GPU machine for that run, streams output, returns JSON, then terminates the machine. You do not log into the machine, pick a region, or keep a box warm.

Human manual: `https://docs.compute.cx`

MCP (stdio): `compute mcp` after the CLI is installed and signed in. MCP (hosted, Streamable HTTP): `https://mcp.compute.cx/mcp` — no local install; use when the caller cannot spawn a local process.

## Rules

- GPU runs spend **prepaid credit**. Confirm the quote. `--yes` and MCP `compute_run` with `confirm_spend=true` skip the interactive confirmation and still spend.
- `--dry-run` and MCP `compute_dry_run` print the upload plan. Nothing is uploaded. **No machine is created.**
- Do not invent files. The first example below is complete; write it to disk before `compute run` or `compute_dry_run`.
- Do not paste `COMPUTE_API_KEY`, `~/.compute/config.toml`, Checkout session ids, or secret values into chat logs.
- Do not use `pip install compute`. v0.1 install is `curl|sh` only.
- Live SKUs come from `compute gpu list`, MCP `compute_list_gpus`, and https://compute.cx/gpus. Do not pass a name that list does not show. `--gpu` may be a SKU, `PROVIDER/SKU`, or a policy: `auto`, `fast`, `cheap` (`fastest` / `cheapest` also accepted). Policies pick from the live catalog — confirm the quoted SKU and rate before spend. Public reserved lead is **H100-SXM** (`H100` and `H100-80GB` are aliases). **MI300X** is AMD. Vast.ai spot SKUs include **RTX-3090**, **RTX-4090**, **RTX-5090**, **L4**, **A100-40GB**, **A100-80GB**, and **H100-SXM** — pass `--provider vastai` or `vastai/<SKU>`. Spot capacity can be reclaimed; Compute then ends the run and tears the machine down. Do not invent a $/hr number; use `compute gpu list` or `compute_list_gpus`.
- One active run per account. Spend, create-rate, and provider capacity can refuse a create even with a positive balance.

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

Prefer `compute_dry_run` then `compute_run` (with `confirm_spend=true`) when the working tree has the entrypoint file: the local server reads it from disk to build the upload. (The hosted server below takes the source inline instead.) `compute_run` without `confirm_spend=true` must be treated as a refusal.

One-click Cursor deeplink (after the CLI is on PATH):

`cursor://anysphere.cursor-deeplink/mcp/install?name=compute&config=eyJjb21tYW5kIjoiY29tcHV0ZSIsImFyZ3MiOlsibWNwIl19`

Portable Agent Plugin (skill + MCP install): the public docs repo `theoriclabs/docs.compute.cx` (`plugin.json`, `mcp.json`, `skills/compute/SKILL.md`). Submit/install from [Cursor Marketplace](https://cursor.com/marketplace) or a team marketplace that imports that repo.

### Hosted (Streamable HTTP + OAuth)

`https://mcp.compute.cx/mcp` — for cloud/hosted agents (Claude.ai- or ChatGPT-style connectors, background agents) that cannot spawn a local process. No CLI install, no `COMPUTE_API_KEY`.

Auth is Clerk OAuth 2.1 + PKCE with Dynamic Client Registration. Discover it from `https://mcp.compute.cx/.well-known/oauth-protected-resource/mcp`; a request without a valid token gets `401` with a `WWW-Authenticate` header pointing at that same discovery document. The authorization server (`https://clerk.compute.cx`) publishes a `registration_endpoint`, so an MCP host can self-register a client and complete the browser consent without anything pre-registered. The consent signs in the Compute account whose prepaid credit the runs will spend.

Full tool set (21): `compute_whoami`, `compute_credits`, `compute_credits_add`, `compute_usage`, `compute_list_gpus`, `compute_dry_run`, `compute_run`, `compute_list_runs`, `compute_get_run`, `compute_get_logs`, `compute_get_result`, `compute_get_receipt`, `compute_cancel_run`, `compute_list_machines`, `compute_delete_machine`, `compute_list_secrets`, `compute_set_secret`, `compute_delete_secret`, `compute_list_artifacts`, `compute_report_issue`, `compute_get_report`. `compute_dry_run` and `compute_run` take the Python source **inline** instead of reading disk: `entrypoint` (`file.py::function`) plus `files`, an array of `{path, content}` holding the entrypoint and every local module it imports (at most 64 `.py` files, 2 MiB total). Third-party packages go in `pip`, not in `files`. `compute_dry_run` uploads nothing and creates no machine; `compute_run` still requires `confirm_spend=true` and spends prepaid credit.

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

## Dry-run, then pay

See what would ship. This must not create a machine:

```bash
compute run simple_mlp.py::train --gpu H100-SXM --dry-run
```

MCP: `compute_dry_run` with `entrypoint=simple_mlp.py::train` and `gpu=H100-SXM`.

NVIDIA image: `compute.Image.cuda_pytorch()`. AMD / MI300X: `compute.Image.rocm_pytorch()`. Mixing them is a failed run.

When the user has credit and wants a real run:

```bash
compute gpu list
compute run simple_mlp.py::train --gpu H100-SXM --wait --yes --args '{"steps": 40, "seed": 20260814}'
compute run simple_mlp.py::train --provider vastai --gpu RTX-4090 --wait --yes
```

MCP: `compute_list_gpus`, then `compute_run` with `confirm_spend=true` and optional `wait=true`.

- `--wait` / `wait=true` streams until a terminal state and prints JSON.
- Without `--wait`, the CLI/MCP exits after create. Follow later with `compute logs <run_id> -f` or `compute_get_logs`.
- `--yes` / `confirm_spend=true` is for non-interactive execution. Tell the user it bypasses the price prompt and will spend credit.
- If the terminal is interactive and the user did not opt out, omit `--yes` so they can confirm spend.

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

MCP: `compute_list_runs`, `compute_get_run`, `compute_get_result`, `compute_get_receipt`, `compute_get_logs`, `compute_list_artifacts`, `compute_cancel_run`, `compute_list_machines`.

Files the job writes under `$COMPUTE_ARTIFACT_DIR` with a `.compute-artifact.json` marker are uploaded to object storage before teardown. After the machine is gone, `compute artifacts get` is how the user retrieves them.

`compute machines` / `compute_list_machines` should be empty after teardown. That is expected.

## If create is refused

Keep the request id from the error body, `compute doctor --json`, or `compute_doctor`, plus the run id if one exists. Send those to the human; do not invent a status page. See [Support](https://docs.compute.cx/support).
