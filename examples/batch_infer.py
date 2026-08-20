import compute

app = compute.App("batch-infer")
image = compute.Image.rocm_pytorch().pip_install("transformers", "accelerate")

DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_PROMPTS = [
    "Complete the sequence: 1, 1, 2, 3, 5,",
    "Name three primary colors.",
    "In one sentence, what is a GPU?",
]


@app.function(gpu="MI300X", image=image, timeout=1800)
def generate(
    prompts: list | None = None,
    model_id: str = DEFAULT_MODEL,
    max_new_tokens: int = 64,
    batch_size: int = 4,
) -> dict:
    import time

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError("this entrypoint needs a GPU")

    prompt_list = list(prompts) if prompts is not None else list(DEFAULT_PROMPTS)
    if not prompt_list:
        raise ValueError("prompts must be a non-empty list of strings")
    for index, prompt in enumerate(prompt_list):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"prompts[{index}] must be a non-empty string")
    if batch_size < 1 or max_new_tokens < 1:
        raise ValueError("batch_size and max_new_tokens must be >= 1")

    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
    ).to("cuda")
    model.eval()
    t_loaded = time.time()

    def format_prompt(text: str) -> str:
        if not hasattr(tokenizer, "apply_chat_template"):
            return text
        try:
            return tokenizer.apply_chat_template(
                [{"role": "user", "content": text}],
                tokenize=False,
                add_generation_prompt=True,
            )
        except Exception:
            return text

    generations: list[dict] = []
    for start in range(0, len(prompt_list), batch_size):
        chunk = prompt_list[start : start + batch_size]
        encoded = tokenizer(
            [format_prompt(prompt) for prompt in chunk],
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        encoded = {key: value.to("cuda") for key, value in encoded.items()}
        with torch.inference_mode():
            output_ids = model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        prompt_lens = encoded["attention_mask"].sum(dim=1).tolist()
        for prompt, full_ids, prompt_len in zip(chunk, output_ids, prompt_lens, strict=True):
            text = tokenizer.decode(full_ids[int(prompt_len) :], skip_special_tokens=True)
            generations.append({"prompt": prompt, "text": text.strip()})

    if torch.cuda.is_available():
        torch.cuda.synchronize()
    t_end = time.time()
    return {
        "ok": True,
        "method": "batch_generate",
        "model_id": model_id,
        "device": torch.cuda.get_device_name(0),
        "n_prompts": len(prompt_list),
        "max_new_tokens": max_new_tokens,
        "batch_size": batch_size,
        "generations": generations,
        "load_s": round(t_loaded - t0, 3),
        "generate_s": round(t_end - t_loaded, 3),
        "wall_s": round(t_end - t0, 3),
    }
