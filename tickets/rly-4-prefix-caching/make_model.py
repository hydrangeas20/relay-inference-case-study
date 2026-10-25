"""Build the RLY-4 test model: a small Qwen2-architecture GGUF with seeded random weights.

Why random weights: this sandbox can't download pretrained weights (Hugging Face is
blocked), and RLY-4 asks a question that doesn't depend on what the weights learned.
Prefill cost and prefix-cache reuse depend on the architecture, the tokenizer and the
token sequence, not on the values in the matrices. Output text from this model is
meaningless, so no result produced with it says anything about completion quality.

The tokenizer is real: every `tokenizer.*` field is copied from llama.cpp's
`models/ggml-vocab-qwen2.gguf` (the Qwen2 BPE vocabulary, also used by Qwen2.5-Coder),
so prompt token counts are what a Qwen2-family code model would see.

Usage (gguf-py from the same llama.cpp checkout as the server):
  PYTHONPATH=$LLAMA_CPP/gguf-py uv run python tickets/rly-4-prefix-caching/make_model.py \
      --vocab $LLAMA_CPP/models/ggml-vocab-qwen2.gguf --out models/relay-rly4-qwen2-synthetic.gguf

The same arguments and seed always produce a byte-identical file; its SHA-256 is printed
and recorded in every run manifest by the server's /props model path.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import gguf  # type: ignore[import-not-found]
import numpy as np


@dataclass(frozen=True)
class Arch:
    n_embd: int = 512
    n_layer: int = 8
    n_head: int = 8
    n_head_kv: int = 2
    n_ff: int = 1536
    n_ctx_train: int = 32768
    rope_freq_base: float = 1_000_000.0
    rms_eps: float = 1e-6
    init_std: float = 0.02
    seed: int = 4  # RLY-4

    @property
    def head_dim(self) -> int:
        return self.n_embd // self.n_head

    @property
    def n_embd_kv(self) -> int:
        return self.head_dim * self.n_head_kv


def _copy_tokenizer(reader: Any, writer: Any) -> int:
    copied = 0
    for name, field in reader.fields.items():
        if not name.startswith("tokenizer."):
            continue
        vtype = field.types[0]
        sub = field.types[-1] if vtype == gguf.GGUFValueType.ARRAY else None
        writer.add_key_value(name, field.contents(), vtype, sub_type=sub)
        copied += 1
    if copied == 0:
        raise ValueError("vocab file has no tokenizer.* fields")
    return copied


def build(vocab_path: Path, out: Path, arch: Arch) -> str:
    reader = gguf.GGUFReader(vocab_path)
    tokens = reader.fields["tokenizer.ggml.tokens"]
    n_vocab = len(tokens.data)
    rng = np.random.default_rng(arch.seed)

    def w(*shape: int) -> np.ndarray:
        return (rng.standard_normal(shape, dtype=np.float32) * arch.init_std).astype(np.float16)

    def ones(n: int) -> np.ndarray:
        return np.ones(n, dtype=np.float32)

    def zeros(n: int) -> np.ndarray:
        return np.zeros(n, dtype=np.float32)

    out.parent.mkdir(parents=True, exist_ok=True)
    writer = gguf.GGUFWriter(str(out), "qwen2")
    writer.add_name("relay-rly4-qwen2-synthetic")
    writer.add_description(
        "Qwen2 architecture, seeded random weights, real Qwen2 tokenizer. "
        "For latency and cache-mechanism experiments only; outputs are meaningless."
    )
    writer.add_context_length(arch.n_ctx_train)
    writer.add_embedding_length(arch.n_embd)
    writer.add_block_count(arch.n_layer)
    writer.add_feed_forward_length(arch.n_ff)
    writer.add_head_count(arch.n_head)
    writer.add_head_count_kv(arch.n_head_kv)
    writer.add_rope_freq_base(arch.rope_freq_base)
    writer.add_layer_norm_rms_eps(arch.rms_eps)
    writer.add_file_type(gguf.LlamaFileType.MOSTLY_F16)
    _copy_tokenizer(reader, writer)

    # numpy shapes are (out_features, in_features); gguf reverses them into ggml order.
    writer.add_tensor("token_embd.weight", w(n_vocab, arch.n_embd))
    for i in range(arch.n_layer):
        p = f"blk.{i}"
        writer.add_tensor(f"{p}.attn_norm.weight", ones(arch.n_embd))
        writer.add_tensor(f"{p}.attn_q.weight", w(arch.n_embd, arch.n_embd))
        writer.add_tensor(f"{p}.attn_q.bias", zeros(arch.n_embd))
        writer.add_tensor(f"{p}.attn_k.weight", w(arch.n_embd_kv, arch.n_embd))
        writer.add_tensor(f"{p}.attn_k.bias", zeros(arch.n_embd_kv))
        writer.add_tensor(f"{p}.attn_v.weight", w(arch.n_embd_kv, arch.n_embd))
        writer.add_tensor(f"{p}.attn_v.bias", zeros(arch.n_embd_kv))
        writer.add_tensor(f"{p}.attn_output.weight", w(arch.n_embd, arch.n_embd))
        writer.add_tensor(f"{p}.ffn_norm.weight", ones(arch.n_embd))
        writer.add_tensor(f"{p}.ffn_gate.weight", w(arch.n_ff, arch.n_embd))
        writer.add_tensor(f"{p}.ffn_up.weight", w(arch.n_ff, arch.n_embd))
        writer.add_tensor(f"{p}.ffn_down.weight", w(arch.n_embd, arch.n_ff))
    writer.add_tensor("output_norm.weight", ones(arch.n_embd))
    writer.add_tensor("output.weight", w(n_vocab, arch.n_embd))

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    return hashlib.sha256(out.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vocab", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    arch = Arch()
    digest = build(args.vocab, args.out, arch)
    print(f"wrote {args.out}")
    print(f"arch {asdict(arch)}")
    print(f"sha256 {digest}")


if __name__ == "__main__":
    main()
