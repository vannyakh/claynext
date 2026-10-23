"""LoRA / SFT / QLoRA / DPO config validation. Dry-run only. No GPU job.

Run:
  KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_llm_training_config.py
"""
from __future__ import annotations

from pathlib import Path

from claynext.models.training.config import CONFIG_DIR, validate_config, load_config
from claynext.models.training.trainer import CancelHandle, ResumeState, prepare, start

CONFIGS = (
    "sft_lora_3b.yaml",
    "qlora_7b_8b.yaml",
    "qlora_14b.yaml",
    "dpo_3b.yaml",
)


def test_shipped_configs_validate_as_dry_run():
    for name in CONFIGS:
        result = prepare(CONFIG_DIR / name)
        assert result["validation"]["ok"], result["validation"]["errors"]
        assert result["started"] is False
        assert result["status"] == "dry_run"
        assert result["snapshot"]["seed"] == 13
        assert len(result["snapshot"]["config_sha256"]) == 64
        assert result["weights"] is None


def test_approval_does_not_start_3b_7b_or_14b(tmp: Path):
    for name in CONFIGS:
        result = start(CONFIG_DIR / name, approval=True, registry_dir=tmp / name)
        assert result["started"] is False
        assert result["status"] == "refused"
        assert result["approval_seen"] is True
        assert result["weights"] is None
    dry = start(CONFIG_DIR / "sft_lora_3b.yaml", approval=False)
    assert dry["status"] == "dry_run"
    assert dry["started"] is False


def test_cancel_and_resume_shapes(tmp: Path):
    handle = CancelHandle()
    handle.cancel()
    cancelled = start(CONFIG_DIR / "sft_lora_3b.yaml", approval=True, cancel=handle)
    assert cancelled["status"] == "cancelled"
    assert cancelled["started"] is False
    prepared = prepare(CONFIG_DIR / "dpo_3b.yaml")
    resume = ResumeState(
        step=0,
        config_sha256=prepared["snapshot"]["config_sha256"],
        seed=13,
        checkpoint_path=None,
    )
    resumed = start(CONFIG_DIR / "dpo_3b.yaml", approval=False, resume=resume, registry_dir=tmp)
    assert resumed["resume"]["accepted"] is True
    assert resumed["started"] is False
    bad = start(
        CONFIG_DIR / "dpo_3b.yaml",
        approval=True,
        resume=ResumeState(step=4, config_sha256="0" * 64, seed=13),
    )
    assert bad["status"] == "refused"
    assert bad["resume"]["accepted"] is False


def test_tune_on_test_is_invalid(tmp: Path):
    path = tmp / "bad.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "schema_version: '1.0.0'\n"
        "method: sft_lora\n"
        "base_model_size_class: tiny\n"
        "base_model_id: tiny-local\n"
        "seed: 1\n"
        "dry_run_default: true\n"
        "approval_required: true\n"
        "tune_on_test: true\n"
        "train_split: test\n"
        "held_out_split: train\n"
        "hardware:\n"
        "  ram_gb: 16\n",
        encoding="utf-8",
    )
    check = validate_config(load_config(path))
    assert check["ok"] is False
    assert "tune_on_test" in check["errors"]
    assert "test_split_misuse" in check["errors"]


def test_tiny_approval_still_does_not_launch(tmp: Path):
    path = tmp / "tiny.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "schema_version: '1.0.0'\n"
        "method: sft_lora\n"
        "base_model_size_class: tiny\n"
        "base_model_id: tiny-local\n"
        "seed: 3\n"
        "dry_run_default: true\n"
        "approval_required: true\n"
        "tune_on_test: false\n"
        "train_split: train\n"
        "held_out_split: test\n"
        "hardware:\n"
        "  ram_gb: 16\n",
        encoding="utf-8",
    )
    result = start(path, approval=True)
    assert result["started"] is False
    assert result["status"] == "refused"
    assert result["weights"] is None


if __name__ == "__main__":
    import sys
    import tempfile
    import traceback

    failed = 0
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        tests = [
            ("test_shipped_configs_validate_as_dry_run", test_shipped_configs_validate_as_dry_run),
            ("test_approval_does_not_start_3b_7b_or_14b", lambda: test_approval_does_not_start_3b_7b_or_14b(tmp)),
            ("test_cancel_and_resume_shapes", lambda: test_cancel_and_resume_shapes(tmp / "resume")),
            ("test_tune_on_test_is_invalid", lambda: test_tune_on_test_is_invalid(tmp / "bad")),
            ("test_tiny_approval_still_does_not_launch", lambda: test_tiny_approval_still_does_not_launch(tmp / "tiny")),
        ]
        for name, fn in tests:
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
