---
name: compute
description: Run a Python function on a fresh cloud GPU with the Compute CLI (compute.cx). Use when installing Compute, signing in, adding prepaid credit, dry-running a payload, submitting a GPU job, following logs, reading a receipt, or canceling a run. Runs spend prepaid credit; --dry-run creates no machine.
---

# Compute

Canonical skill URL: `https://compute.cx/SKILL.md`

Compute uploads a Python function, provisions a **new** GPU machine for that run, streams output, returns JSON, then terminates the machine. You do not SSH in, pick a region, or keep a box warm.

Human manual: `https://docs.compute.cx`

## Rules

- GPU runs spend **prepaid credit**. Confirm the quote. `--yes` skips the interactive confirmation and still spends.
- `--dry-run` prints the upload plan. Nothing is uploaded. **No machine is created.**
- Do not invent files. The first example below is complete; write it to disk before `compute run`.
- Do not paste `COMPUTE_API_KEY`, `~/.compute/config.toml`, or Checkout session ids into chat logs.
- Do not use `pip install compute`. v0.1 install is `curl|sh` only.
- Live SKUs come from `compute gpu list`. Do not pass a name that list does not show. Public lead is **H100-SXM** (`H100` and `H100-80GB` are aliases). **MI300X** exists; stock can be tight.
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

## Credit

Minimum Checkout is **$10**. Balance updates after the payment webhook, not when the Checkout tab opens.

```bash
compute credits add 10
compute credits
```

A run is refused if the hold would exceed remaining credit or a spend cap. Billing is started minutes while the machine exists, plus a platform fee. Failed boots that never start the machine are $0. Do not hard-code a fee percentage; use [Pricing](https://compute.cx/pricing) and `compute runs receipt <run_id>`.

## First example

Save this file as `simple_mlp.py` in the working directory (also at `https://docs.compute.cx/examples/simple_mlp.py` and in [First run](https://docs.compute.cx/get-started/first-run)):

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

NVIDIA image: `compute.Image.cuda_pytorch()`. AMD / MI300X: `compute.Image.rocm_pytorch()`. Mixing them is a failed run.

When the user has credit and wants a real run:

```bash
compute gpu list
compute run simple_mlp.py::train --gpu H100-SXM --wait --yes --args '{"steps": 40, "seed": 20260814}'
```

- `--wait` streams until a terminal state and prints JSON.
- Without `--wait`, the CLI exits after create. Follow later with `compute logs <run_id> -f`.
- `--yes` is for non-interactive execution. Tell the user it bypasses the price prompt and will spend credit.
- If the terminal is interactive and the user did not opt out, omit `--yes` so they can confirm spend.

## Inspect and tear down

```bash
compute runs list
compute runs status <run_id>
compute runs result <run_id>
compute runs receipt <run_id>
compute logs <run_id> -f
compute cancel <run_id>
compute machines
```

`compute machines` should be empty after teardown. That is expected.

## If create is refused

Keep the request id from the error body or `compute doctor --json`, plus the run id if one exists. Send those to the human; do not invent a status page. See [Support](https://docs.compute.cx/support).
