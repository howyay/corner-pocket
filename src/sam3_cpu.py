"""SAM3 on CPU.

The official SAM3 code hardcodes CUDA in a few eager setup paths that are
unnecessary for inference (position-encoding precompute).  We monkeypatch them
to skip eager precompute (the cache is filled lazily on the device actually
used), which lets the model run on CPU.  No weights are modified.
"""
from __future__ import annotations

from pathlib import Path
import types  # noqa: F401


def _apply_patches() -> None:
    import torch  # noqa: F401  (ensures torch imported first)
    import sam3.model.position_encoding as pe

    orig_init = pe.PositionEmbeddingSine.__init__

    def _patched_init(self, *args, precompute_resolution=None, **kwargs):
        # Skip eager precompute on cuda: the original `forward` fills the cache
        # lazily on the device of its input, which works on CPU.
        orig_init(self, *args, precompute_resolution=None, **kwargs)

    pe.PositionEmbeddingSine.__init__ = _patched_init

    # The fused fc1+activation kernel casts to bfloat16 (GPU-oriented) and
    # would otherwise fail / be wrong on CPU.  Replace with plain float32 ops.
    import sam3.perflib.fused as fused
    import torch.nn as nn

    def _addmm_act_cpu(activation, linear, mat1):
        y = nn.functional.linear(mat1, linear.weight, linear.bias)
        if activation in (nn.functional.relu, nn.ReLU):
            return nn.functional.relu(y)
        if activation in (nn.functional.gelu, nn.GELU):
            return nn.functional.gelu(y)
        raise ValueError(f"Unexpected activation {activation}")

    fused.addmm_act = _addmm_act_cpu
    # Import-order proof: vitdet may have been imported before this rebind
    # (e.g. by the server's sam3 model import chain); fix its binding too.
    import sam3.model.vitdet as _vitdet
    _vitdet.addmm_act = _addmm_act_cpu

    # pin_memory() requires a CUDA-capable accelerator in recent torch; on CPU
    # it is a no-op, so make it safe for the image path.
    _orig_pin = torch.Tensor.pin_memory

    def _pin_memory_noop(self, device=None):
        return self

    torch.Tensor.pin_memory = _pin_memory_noop


def load_sam3_image_model(checkpoint_path: str, device: str = "cpu", **kwargs):
    import torch
    """Build the SAM3 image model on CPU with the CUDA patch applied."""
    _apply_patches()
    from sam3.model_builder import build_sam3_image_model

    if "bpe_path" not in kwargs or kwargs["bpe_path"] is None:
        kwargs["bpe_path"] = (
            Path(__file__).resolve().parent / "sam3" / "sam3" / "assets" / "bpe_simple_vocab_16e6.txt.gz"
        )

    model = build_sam3_image_model(
        bpe_path=kwargs.pop("bpe_path"),
        device=device,
        eval_mode=True,
        checkpoint_path=checkpoint_path,
        load_from_HF=False,
        **kwargs,
    )
    if device != "cpu":
        # Measured on this stack (RX 9070 XT, ROCm torch): the SAM3 detection
        # head returns zero instances on GPU in every dtype configuration,
        # while the CPU path is verified (10 balls).  SAM3 stays on CPU.
        model = model.to(device=device, dtype=torch.float32)
        model._fp32_gpu = True
    return model


def make_processor(model, device: str = "cpu", resolution: int = 1008):

    from sam3.model.sam3_image_processor import Sam3Processor

    return Sam3Processor(model, resolution=resolution, device=device)


if __name__ == "__main__":
    import time

    t0 = time.time()
    model = load_sam3_image_model("data/sam3.safetensors")
    print(f"model loaded in {time.time() - t0:.1f}s", flush=True)
    proc = make_processor(model)
    print("processor ready", flush=True)
