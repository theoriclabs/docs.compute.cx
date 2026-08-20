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
