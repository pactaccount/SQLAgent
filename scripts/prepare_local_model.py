"""Download a pinned MLX checkpoint and save a real inference smoke check."""
import json
from importlib.metadata import version
from pathlib import Path
import time

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]
REPO = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
REVISION = "019cc73c45c770444708a6dd8690c66243cc5c80"


def main():
    destination = ROOT / "models" / "qwen2.5-coder-7b-instruct-4bit"
    output = ROOT / "artifacts" / "setup"
    output.mkdir(parents=True, exist_ok=True)
    print("Downloading pinned model; rerunning resumes cached downloads.", flush=True)
    snapshot_download(repo_id=REPO, revision=REVISION, local_dir=destination)
    manifest = {
        "repository": REPO,
        "revision": REVISION,
        "path": str(destination),
        "packages": {p: version(p) for p in ("mlx", "mlx-lm", "huggingface-hub")},
    }
    (output / "model_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    from mlx_lm import load, generate
    from mlx_lm.sample_utils import make_sampler

    print("Loading model and checking generation...", flush=True)
    model, tokenizer = load(str(destination))
    question = (
        "Return only SQLite SQL. Table orders(order_id TEXT, order_status TEXT). "
        "Count orders by order_status, sorted by order_status."
    )
    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": question}],
        tokenize=False,
        add_generation_prompt=True,
    )
    started = time.perf_counter()
    answer = generate(model, tokenizer, prompt=prompt, max_tokens=128,
                      sampler=make_sampler(temp=0.0), verbose=True)
    result = {"question": question, "answer": answer,
              "generation_seconds": time.perf_counter() - started,
              "note": "Inference smoke check only; not benchmark accuracy."}
    (output / "inference_smoke.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Saved manifest and inference output to {output}", flush=True)


if __name__ == "__main__":
    main()
