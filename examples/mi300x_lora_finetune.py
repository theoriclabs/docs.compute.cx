import inspect

import compute

app = compute.App("mi300x-lora")
image = compute.Image.rocm_pytorch().pip_install(
    "transformers",
    "peft",
    "datasets",
    "trl",
    "accelerate",
)

DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_DATASET = "yahma/alpaca-cleaned"


@app.function(gpu="MI300X", image=image, timeout=1800)
def finetune(
    model_id: str = DEFAULT_MODEL,
    dataset_id: str = DEFAULT_DATASET,
    max_steps: int = 1,
    sample_count: int = 16,
    lr: float = 2e-4,
    rank: int = 8,
    max_seq_length: int = 512,
) -> dict:
    import time

    import torch
    from datasets import load_dataset
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    if not torch.cuda.is_available():
        raise RuntimeError("this entrypoint needs a GPU")

    tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.bfloat16)
    model.to("cuda")
    model.config.use_cache = False
    model = get_peft_model(
        model,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=rank,
            lora_alpha=rank * 2,
            lora_dropout=0.05,
            bias="none",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        ),
    )
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    raw = load_dataset(dataset_id, split=f"train[:{sample_count}]")

    def to_text(example: dict) -> dict:
        instruction = example.get("instruction") or ""
        extra = example.get("input") or ""
        output = example.get("output") or ""
        if extra:
            text = (
                f"### Instruction:\n{instruction}\n\n### Input:\n{extra}\n\n"
                f"### Response:\n{output}"
            )
        else:
            text = f"### Instruction:\n{instruction}\n\n### Response:\n{output}"
        return {"text": text}

    dataset = raw.map(to_text, remove_columns=raw.column_names)

    length_params = inspect.signature(SFTConfig.__init__).parameters
    length_kw = (
        {"max_length": max_seq_length}
        if "max_length" in length_params
        else {"max_seq_length": max_seq_length}
    )
    trainer_params = inspect.signature(SFTTrainer.__init__).parameters
    tokenizer_kw = (
        {"processing_class": tokenizer}
        if "processing_class" in trainer_params
        else {"tokenizer": tokenizer}
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        args=SFTConfig(
            output_dir="/tmp/lora-sft",
            dataset_text_field="text",
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=min(2, max_steps),
            max_steps=max_steps,
            learning_rate=lr,
            logging_steps=1,
            bf16=True,
            optim="adamw_torch",
            report_to="none",
            save_strategy="no",
            gradient_checkpointing=True,
            **length_kw,
        ),
        **tokenizer_kw,
    )

    t0 = time.perf_counter()
    metrics = trainer.train().metrics
    return {
        "ok": True,
        "method": "sft",
        "model_id": model_id,
        "dataset_id": dataset_id,
        "max_steps": max_steps,
        "sample_count": sample_count,
        "device": torch.cuda.get_device_name(0),
        "train_loss": float(metrics.get("train_loss", 0.0)),
        "wall_s": round(time.perf_counter() - t0, 3),
    }
