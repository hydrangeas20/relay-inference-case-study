"""Figures for the queueing diagnosis (reads analysis/results/diagnosis-queueing/diagnosis.json).

Usage: uv run --with matplotlib python analysis/plot_diagnosis.py
(matplotlib isn't a project dependency; it's only needed for these figures.)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

DIR = Path("analysis/results/diagnosis-queueing")
# Validated categorical order (dataviz reference palette, light mode): fixed per entity.
COLOR = {"Azure": "#2a78d6", "C1": "#eb6834", "C2": "#1baf7a", "Poisson": "#eda100"}
INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6a64", "#e4e3dc", "#fcfcfb"
CELL_LABEL = {"0.2_0.6": "service 0.2 s, ρ 0.6", "0.2_0.8": "service 0.2 s, ρ 0.8",
              "1.0_0.6": "service 1.0 s, ρ 0.6", "1.0_0.8": "service 1.0 s, ρ 0.8"}  # fmt: skip

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold", "legend.frameon": False,
})  # fmt: skip


def ratio(a: float, b: float, s: float) -> float:
    return a / b if a >= 0.01 * s and b >= 0.01 * s else float("nan")


def fig_queue_error(d: dict[str, Any]) -> None:
    """Median (and IQR) over Thursday hours of p99 / Azure p99, per condition."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    cells = list(CELL_LABEL)
    ax.axvspan(0.67, 1.5, color="#eeede6", zorder=0, lw=0)
    ax.axvline(1.0, color=MUTED, lw=1, zorder=1)
    for j, name in enumerate(("C1", "C2", "Poisson")):
        for i, cell in enumerate(cells):
            s = float(cell.split("_")[0])
            r = np.array([ratio(h["surrogates"][name]["original"][cell][1],
                                h["surrogates"]["Azure"]["original"][cell][1], s)
                          for h in d["thursday"]])  # fmt: skip
            r = r[~np.isnan(r)]
            y = i + (j - 1) * 0.22
            lo, med, hi = np.percentile(r, [25, 50, 75])
            ax.plot([lo, hi], [y, y], color=COLOR[name], lw=2, solid_capstyle="round", zorder=2)
            ax.plot(med, y, "o", ms=8, color=COLOR[name], mec=SURFACE, mew=2, zorder=3,
                    label=name if i == 0 else None)  # fmt: skip
            if name != "Poisson":
                ax.annotate(f"{med:.2f}", (med, y), xytext=(6, -3), textcoords="offset points",
                            fontsize=8, color=INK)  # fmt: skip
    ax.set_xscale("log")
    ax.set_xticks([0.1, 0.2, 0.5, 1, 2, 5])
    ax.set_xticklabels(["0.1×", "0.2×", "0.5×", "1×", "2×", "5×"])
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xlim(0.08, 6)
    ax.set_yticks(range(len(cells)))
    ax.set_yticklabels([CELL_LABEL[c] for c in cells])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("p99 wait ÷ Azure p99 wait (median and IQR over 24 Thursday hours)")
    ax.set_title("Queue tails: both candidates overshoot, Poisson undershoots", loc="left")
    ax.text(0.69, 3.6, "acceptance band\n0.67–1.5×", fontsize=8, color=MUTED, va="center")
    ax.set_ylim(3.75, -0.5)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncols=3, fontsize=9)
    fig.tight_layout()
    fig.savefig(DIR / "fig1-queue-error-by-condition.png", dpi=160)


def fig_block_shuffle(d: dict[str, Any]) -> None:
    blocks = [1, 5, 15, 30, 60, 0]
    labels = ["1", "5", "15", "30", "60", "none"]
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.4), sharey=True)
    for ax, cell in zip(axes, ("0.2_0.8", "1.0_0.8"), strict=True):
        s = float(cell.split("_")[0])
        for name in ("C1", "C2"):
            ys = []
            for b in blocks:
                r = [ratio(h["block_shuffle_p99"][name][f"{cell}_B{b}"],
                           h["block_shuffle_p99"]["Azure"][f"{cell}_B{b}"], s) for h in d["thursday"]]  # fmt: skip
                ys.append(float(np.nanmedian(r)))
            ax.plot(range(len(blocks)), ys, "-o", color=COLOR[name], lw=2, ms=6, mec=SURFACE,
                    mew=1.5, label=name)  # fmt: skip
            ax.annotate(name, (len(blocks) - 1, ys[-1]), xytext=(6, 0), textcoords="offset points",
                        fontsize=9, color=INK, va="center")  # fmt: skip
        ax.axhline(1.0, color=MUTED, lw=1)
        ax.set_xticks(range(len(blocks)))
        ax.set_xticklabels(labels)
        ax.set_xlabel("block size kept intact when shuffling (s)")
        ax.set_title(CELL_LABEL[cell], loc="left", fontsize=10)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("model ÷ Azure p99 (median over hours)")
    fig.suptitle("Overshoot grows as 5–60 s structure is kept", x=0.02, ha="left",
                 fontweight="bold", fontsize=11)  # fmt: skip
    fig.tight_layout()
    fig.savefig(DIR / "fig2-block-shuffle.png", dpi=160)


def fig_persistence(d: dict[str, Any]) -> None:
    lags = [1, 2, 5, 10, 20, 30]
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.4), sharey=True)
    for ax, (key, title) in zip(axes, (("top5", "High-rate states (top 5%)"),
                                       ("bottom5", "Low-rate states (bottom 5%)")), strict=True):  # fmt: skip
        for name in ("Azure", "C1", "Poisson"):
            ys = [float(np.median([h["stats"][name][f"persist_{key}_{lag}"] for h in d["training"]]))
                  for lag in lags]  # fmt: skip
            ax.plot(lags, ys, "-o", color=COLOR[name], lw=2, ms=6, mec=SURFACE, mew=1.5, label=name)
        ax.axhline(0.05, color=MUTED, lw=1, ls=(0, (3, 3)))
        ax.set_xscale("log")
        ax.set_xticks(lags)
        ax.set_xticklabels([str(x) for x in lags])
        ax.set_xlabel("lag (s)")
        ax.set_title(title, loc="left", fontsize=10)
    axes[0].set_ylabel("P(still in state after lag)")
    axes[0].text(1, 0.065, "chance 0.05", fontsize=8, color=MUTED)
    axes[1].legend(loc="upper right", fontsize=9)
    fig.suptitle("C1 keeps high-rate states longer than Azure; low-rate states match (training, 119 h)",
                 x=0.02, ha="left", fontweight="bold", fontsize=11)  # fmt: skip
    fig.tight_layout()
    fig.savefig(DIR / "fig3-tail-persistence.png", dpi=160)


def fig_surrogates(d: dict[str, Any]) -> None:
    variants = [("original", "C1 as generated"),
                ("within_second", "C1, arrivals re-placed within each second"),
                ("model_order_azure_marginal", "C1's time order, Azure's per-second counts"),
                ("azure_order_model_marginal", "Azure's time order, C1's per-second counts")]  # fmt: skip
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.2), sharey=True)
    for ax, cell in zip(axes, ("0.2_0.8", "1.0_0.8"), strict=True):
        s = float(cell.split("_")[0])
        vals = []
        for key, _ in variants:
            r = [ratio(h["surrogates"]["C1"][key][cell][1], h["surrogates"]["Azure"]["original"][cell][1], s)
                 for h in d["thursday"]]  # fmt: skip
            vals.append(float(np.nanmedian(r)))
        y = np.arange(len(variants))
        ax.barh(y, vals, height=0.6, color=COLOR["C1"], edgecolor=SURFACE, linewidth=2)
        for yi, v in zip(y, vals, strict=True):
            ax.text(v + 0.02, yi, f"{v:.2f}×", va="center", fontsize=9, color=INK)
        ax.axvline(1.0, color=MUTED, lw=1)
        ax.set_title(CELL_LABEL[cell], loc="left", fontsize=10)
        ax.set_xlabel("p99 ÷ Azure p99 (median over hours)")
        ax.grid(axis="y", visible=False)
        ax.set_xlim(0, max(vals) * 1.25)
    axes[0].set_yticks(range(len(variants)))
    axes[0].set_yticklabels([v[1] for v in variants], fontsize=9)
    axes[0].invert_yaxis()
    fig.suptitle("Sub-second placement doesn't matter; count distribution and time order both do",
                 x=0.02, ha="left", fontweight="bold", fontsize=11)  # fmt: skip
    fig.tight_layout()
    fig.savefig(DIR / "fig4-surrogates.png", dpi=160)


def main() -> None:
    d = json.loads((DIR / "diagnosis.json").read_text())
    fig_queue_error(d)
    fig_block_shuffle(d)
    fig_persistence(d)
    fig_surrogates(d)
    print(f"wrote figures to {DIR}")


if __name__ == "__main__":
    main()
