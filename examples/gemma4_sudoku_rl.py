# SPDX-License-Identifier: LGPL-3.0-only
"""Gemma 4 E2B Sudoku GRPO on Compute.

Adapted from Unsloth's Gemma 4 Sudoku notebook:
https://github.com/unslothai/notebooks/blob/main/nb/Gemma4_%28E2B%29_Reinforcement_Learning_Sudoku_Game.ipynb

This adapted example is distributed under the GNU Lesser General Public
License v3.0 only. The main changes package the notebook as one Compute
function, pin the tested dependency set, add argument validation, and return
JSON metrics suitable for ``compute run --wait``.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Callable
from typing import Any

import compute

app = compute.App("gemma4-sudoku-grpo")

# Dependencies install inside the function so failures appear in the run log.
# This also preserves the upstream notebook's two-stage --no-deps upgrade.
image = compute.Image.cuda_pytorch()

DEFAULT_MODEL = "unsloth/gemma-4-E2B-it"
SUDOKU_PROMPT = """
Create a Sudoku solving strategy using only native Python built-in functions
without any import statements.

You are given two lists of lists (9x9 grids):
- board: current state (0 means empty)
- initial: starting puzzle (0 means was empty, numbers are fixed)

Return a tuple (row, col, number) for the next move.
- row: 0-8 (row index)
- col: 0-8 (column index)
- number: 1-9 (digit to place)

Only place numbers in cells that are BOTH empty in initial AND empty in board
(initial[row][col] == 0 AND board[row][col] == 0).
Use Sudoku rules: no duplicates in rows, columns, or 3x3 boxes.
Output your function in backticks:
```python
def strategy(board, initial):
    # Your logic here
    return (row, col, number)
```
All helper functions must be inside def strategy. Output only the function.
""".strip()


def _install_training_stack() -> None:
    """Install the base stack, then apply the notebook's no-deps upgrades."""
    import os
    import shutil
    import subprocess
    import sys

    if shutil.which("cc") is None:
        install_env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
        subprocess.run(["apt-get", "update"], check=True, env=install_env)
        subprocess.run(
            ["apt-get", "install", "-y", "--no-install-recommends", "gcc"],
            check=True,
            env=install_env,
        )

    base_packages = [
        "torch==2.10.0",
        "torchvision==0.25.0",
        "unsloth==2026.4.4",
        "unsloth_zoo==2026.4.6",
        "timm==1.0.26",
        "safetensors==0.8.0",
    ]
    notebook_upgrades = [
        "transformers==5.5.4",
        "tokenizers==0.22.2",
        "trl==1.1.0",
        "huggingface_hub==1.9.2",
    ]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--upgrade",
            *base_packages,
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--quiet",
            "--upgrade",
            "--no-deps",
            *notebook_upgrades,
        ],
        check=True,
    )


def _is_valid_placement(
    board: list[list[int]], row: int, col: int, number: int
) -> bool:
    if number in board[row]:
        return False
    if number in (board[r][col] for r in range(9)):
        return False

    box_row = 3 * (row // 3)
    box_col = 3 * (col // 3)
    return all(
        board[r][c] != number
        for r in range(box_row, box_row + 3)
        for c in range(box_col, box_col + 3)
    )


def _solve_sudoku(board: list[list[int]]) -> bool:
    for row in range(9):
        for col in range(9):
            if board[row][col] != 0:
                continue
            for number in range(1, 10):
                if _is_valid_placement(board, row, col, number):
                    board[row][col] = number
                    if _solve_sudoku(board):
                        return True
                    board[row][col] = 0
            return False
    return True


def _generate_complete_board(rng: random.Random) -> list[list[int]]:
    board = [[0 for _ in range(9)] for _ in range(9)]
    for box in range(3):
        numbers = list(range(1, 10))
        rng.shuffle(numbers)
        for i in range(3):
            for j in range(3):
                board[box * 3 + i][box * 3 + j] = numbers[i * 3 + j]
    if not _solve_sudoku(board):
        raise RuntimeError("failed to generate a Sudoku board")
    return board


class SudokuGame:
    def __init__(self, difficulty: int = 40, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._solution = _generate_complete_board(self._rng)
        self._board = copy.deepcopy(self._solution)

        cells = [(row, col) for row in range(9) for col in range(9)]
        self._rng.shuffle(cells)
        for row, col in cells[:difficulty]:
            self._board[row][col] = 0

        self._initial_board = copy.deepcopy(self._board)
        self._moves = 0
        self._state = "ongoing"
        self._update_state()

    def board(self) -> list[list[int]]:
        return copy.deepcopy(self._board)

    def initial_board(self) -> list[list[int]]:
        return copy.deepcopy(self._initial_board)

    def state(self) -> str:
        return self._state

    def place_number(self, row: int, col: int, number: int) -> bool:
        if not (0 <= row < 9 and 0 <= col < 9 and 1 <= number <= 9):
            self._state = "failed"
            return False
        if self._initial_board[row][col] != 0 or self._board[row][col] != 0:
            self._state = "failed"
            return False
        if not _is_valid_placement(self._board, row, col, number):
            self._state = "failed"
            return False

        self._board[row][col] = number
        self._moves += 1
        self._update_state()
        return True

    def _update_state(self) -> None:
        if all(value != 0 for row in self._board for value in row):
            self._state = "success" if self._board == self._solution else "failed"


def _execute_strategy(
    strategy: Callable[[list[list[int]], list[list[int]]], Any], game: SudokuGame
) -> tuple[int, str]:
    valid_moves = 0
    while game.state() == "ongoing" and valid_moves < 100:
        try:
            result = strategy(game.board(), game.initial_board())
            if not isinstance(result, (tuple, list)) or len(result) != 3:
                return valid_moves, "failed"
            row, col, number = result
            if not all(isinstance(item, int) for item in (row, col, number)):
                return valid_moves, "failed"
            if not game.place_number(row, col, number):
                return valid_moves, "failed"
            valid_moves += 1
        except Exception:
            return valid_moves, "failed"
    return valid_moves, game.state()


def _extract_function(text: str) -> str | None:
    if text.count("```") < 2:
        return None
    first = text.find("```") + 3
    second = text.find("```", first)
    function = text[first:second].strip().removeprefix("python\n")
    function = function[function.find("def") :]
    if function.startswith("def strategy(board, initial):"):
        return function
    return None


def _make_reward_functions(
    *, difficulty: int, reward_seed: int
) -> list[Callable[..., list[float]]]:
    from unsloth import (
        check_python_modules,
        create_locked_down_function,
        execute_with_time_limit,
    )

    execute_strategy = execute_with_time_limit(10)(_execute_strategy)
    reward_rng = random.Random(reward_seed)

    def function_works(completions: list[list[dict[str, str]]], **_: Any) -> list[float]:
        scores: list[float] = []
        for completion in completions:
            function = _extract_function(completion[0]["content"])
            if function is None:
                scores.append(-2.0)
                continue
            ok, _info = check_python_modules(function)
            if not ok:
                scores.append(-2.0)
                continue
            try:
                create_locked_down_function(function)
                scores.append(1.0)
            except Exception:
                scores.append(-1.0)
        return scores

    def no_cheating(completions: list[list[dict[str, str]]], **_: Any) -> list[float]:
        scores: list[float] = []
        for completion in completions:
            function = _extract_function(completion[0]["content"])
            if function is None:
                scores.append(-1.0)
                continue
            ok, _info = check_python_modules(function)
            scores.append(1.0 if ok else -20.0)
        return scores

    def strategy_succeeds(
        completions: list[list[dict[str, str]]], **_: Any
    ) -> list[float]:
        scores: list[float] = []
        puzzle_seed = reward_rng.randrange(10_000)
        for completion in completions:
            function = _extract_function(completion[0]["content"])
            if function is None:
                scores.append(0.0)
                continue
            ok, _info = check_python_modules(function)
            if not ok:
                scores.append(0.0)
                continue
            try:
                strategy = create_locked_down_function(function)
                game = SudokuGame(difficulty=difficulty, seed=puzzle_seed)
                valid_moves, state = execute_strategy(strategy, game)
                if state == "success" or valid_moves == difficulty:
                    scores.append(30.0)
                elif valid_moves > 0:
                    scores.append(valid_moves * 0.2)
                else:
                    scores.append(-2.0)
            except TimeoutError:
                scores.append(-1.0)
            except Exception:
                scores.append(-3.0)
        return scores

    return [function_works, no_cheating, strategy_succeeds]


def _train_impl(
    model_id: str = DEFAULT_MODEL,
    max_steps: int = 1,
    dataset_size: int = 64,
    difficulty: int = 40,
    max_seq_length: int = 4096,
    lora_rank: int = 32,
    num_generations: int = 2,
    seed: int = 3407,
) -> dict[str, Any]:
    """Train a Gemma 4 E2B LoRA with GRPO rewards from a Sudoku game."""
    import time
    from pathlib import Path

    if max_steps < 1:
        raise ValueError("max_steps must be >= 1")
    if dataset_size < num_generations:
        raise ValueError("dataset_size must be >= num_generations")
    if not 1 <= difficulty <= 64:
        raise ValueError("difficulty must be between 1 and 64")
    if max_seq_length < 1024:
        raise ValueError("max_seq_length must be >= 1024")
    if lora_rank < 1:
        raise ValueError("lora_rank must be >= 1")
    if num_generations < 2:
        raise ValueError("num_generations must be >= 2")

    _install_training_stack()

    import torch
    import transformers
    import trl
    import unsloth
    from datasets import Dataset
    from safetensors import safe_open
    from trl import GRPOConfig, GRPOTrainer
    from unsloth import FastVisionModel

    if not torch.cuda.is_available():
        raise RuntimeError("this entrypoint requires an NVIDIA CUDA GPU")

    model, tokenizer = FastVisionModel.from_pretrained(
        model_name=model_id,
        max_seq_length=max_seq_length,
        load_in_4bit=False,
        fast_inference=False,
    )
    model = FastVisionModel.get_peft_model(
        model,
        r=lora_rank,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=lora_rank * 2,
        use_gradient_checkpointing="unsloth",
        random_state=seed,
    )

    # The reference notebook's Unsloth Zoo patch makes TRL's temporary
    # checkpointing toggle a no-op. Preserve that compatibility when the
    # automatic patch does not activate in an ephemeral environment.
    enable_gradient_checkpointing = model.gradient_checkpointing_enable

    def enable_gradient_checkpointing_compat(*_args: Any, **_kwargs: Any) -> Any:
        return enable_gradient_checkpointing()

    model.gradient_checkpointing_enable = enable_gradient_checkpointing_compat

    dataset = Dataset.from_list(
        [
            {
                "prompt": [{"role": "user", "content": SUDOKU_PROMPT}],
                "answer": 0,
            }
            for _ in range(dataset_size)
        ]
    )
    prompt_length = len(
        tokenizer.apply_chat_template(
            [{"role": "user", "content": SUDOKU_PROMPT}],
            add_generation_prompt=True,
        )
    )
    max_completion_length = max_seq_length - (prompt_length + 1)
    if max_completion_length < 128:
        raise ValueError(
            "max_seq_length leaves fewer than 128 tokens for the generated strategy"
        )

    output_dir = Path("/tmp/gemma4-sudoku-grpo")
    adapter_dir = Path("/tmp/gemma4-sudoku-lora")
    training_args = GRPOConfig(
        temperature=1.0,
        learning_rate=5e-5,
        weight_decay=0.001,
        warmup_ratio=0.1,
        lr_scheduler_type="linear",
        optim="adamw_8bit",
        logging_steps=1,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=2,
        num_generations=num_generations,
        max_completion_length=max_completion_length,
        max_steps=max_steps,
        save_strategy="no",
        report_to="none",
        output_dir=str(output_dir),
        epsilon=0.2,
        epsilon_high=0.28,
        delta=1.5,
        loss_type="bnpo",
        mask_truncated_completions=True,
        seed=seed,
    )
    trainer = GRPOTrainer(
        model=model,
        processing_class=tokenizer,
        reward_funcs=_make_reward_functions(difficulty=difficulty, reward_seed=seed),
        args=training_args,
        train_dataset=dataset,
    )

    started = time.perf_counter()
    train_output = trainer.train()
    metrics = train_output.metrics

    loss_history: list[dict[str, float | int]] = []
    reward_history: list[dict[str, float | int]] = []
    for fallback_step, entry in enumerate(trainer.state.log_history, start=1):
        step = int(entry.get("step", fallback_step))
        if "loss" in entry:
            loss_history.append({"step": step, "loss": float(entry["loss"])})

        step_rewards = [
            float(value)
            for key, value in entry.items()
            if key.startswith("rewards/") and key.endswith("/mean")
        ]
        if step_rewards:
            reward_history.append(
                {
                    "step": step,
                    "reward_mean": sum(step_rewards) / len(step_rewards),
                }
            )
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)

    adapter_file = adapter_dir / "adapter_model.safetensors"
    tensor_count = 0
    nonzero_tensor_count = 0
    with safe_open(adapter_file, framework="pt") as tensors:
        for key in tensors.keys():
            tensor_count += 1
            if torch.count_nonzero(tensors.get_tensor(key)).item() > 0:
                nonzero_tensor_count += 1
    if tensor_count == 0 or nonzero_tensor_count != tensor_count:
        raise RuntimeError("saved LoRA adapter did not pass the nonzero tensor check")

    reward_keys = sorted(
        key
        for key in metrics
        if key.startswith("rewards/") and key.endswith("/mean")
    )
    reward_values = [float(metrics[key]) for key in reward_keys]
    reward_mean = (
        sum(reward_values) / len(reward_values)
        if reward_values
        else reward_history[-1]["reward_mean"]
        if reward_history
        else None
    )
    return {
        "ok": True,
        "method": "grpo",
        "task": "sudoku",
        "model_id": model_id,
        "device": torch.cuda.get_device_name(0),
        "max_steps": max_steps,
        "dataset_size": dataset_size,
        "difficulty": difficulty,
        "num_generations": num_generations,
        "max_completion_length": max_completion_length,
        "train_loss": float(metrics.get("train_loss", 0.0)),
        "reward_mean": reward_mean,
        "loss_history": loss_history,
        "reward_history": reward_history,
        "adapter_verified": True,
        "adapter_tensor_count": tensor_count,
        "adapter_path": str(adapter_dir),
        "wall_s": round(time.perf_counter() - started, 3),
        "versions": {
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "trl": trl.__version__,
            "unsloth": unsloth.__version__,
        },
    }


@app.function(gpu="H100-SXM", image=image, timeout=3600)
def train(
    model_id: str = DEFAULT_MODEL,
    max_steps: int = 1,
    dataset_size: int = 64,
    difficulty: int = 40,
    max_seq_length: int = 4096,
    lora_rank: int = 32,
    num_generations: int = 2,
    seed: int = 3407,
) -> dict[str, Any]:
    """Run training and preserve remote diagnostics in the JSON result."""
    import traceback

    try:
        return _train_impl(
            model_id=model_id,
            max_steps=max_steps,
            dataset_size=dataset_size,
            difficulty=difficulty,
            max_seq_length=max_seq_length,
            lora_rank=lora_rank,
            num_generations=num_generations,
            seed=seed,
        )
    except Exception as error:
        return {
            "ok": False,
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
