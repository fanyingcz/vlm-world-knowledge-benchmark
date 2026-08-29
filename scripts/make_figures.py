"""Generate the figures used in README.md from results/*.json.

The JSON files in results/ are the analysis output produced by the evaluation
platform; this script reads them and renders the two summary figures so the
numbers in the README are never hand-transcribed.

Usage
-----
    pip install matplotlib
    python scripts/make_figures.py

Outputs
-------
    results/fig_accuracy_by_mode.png
    results/fig_gain_over_baseline.png
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# Model display names, their result files, and plot colours.
MODELS = [
    ("Google Gemini", "cross_subject_Gemini.json", "#1a73e8"),
    ("Doubao (Volcengine)", "cross_subject_Doubao.json", "#e8710a"),
    ("Qwen (Alibaba)", "cross_subject_Qwen.json", "#7c3aed"),
]

MODE_LABELS = [
    "Mode 1\nBaseline",
    "Mode 2\n+ relevant\nknowledge",
    "Mode 3\n+ CoT\nguidance",
    "Mode 4\n+ irrelevant knowledge\n(control)",
]

# Condition names used in the gain figure.
GAIN_LABELS = ["+ relevant\nknowledge", "+ CoT\nguidance", "+ irrelevant\nknowledge (control)"]


def load_mode_accuracy(filename):
    """Return [mode1, mode2, mode3, mode4] accuracy for one model."""
    path = os.path.join(RESULTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)["result"]
    by_mode = {m["test_mode"]: m["accuracy_percent"] for m in data["mode_performance"]}
    return [by_mode[i] for i in (1, 2, 3, 4)]


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#c9ccd4")
    ax.spines["bottom"].set_color("#c9ccd4")
    ax.tick_params(colors="#5f6368", length=4)
    ax.grid(axis="y", color="#eceef1", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def figure_accuracy_by_mode():
    fig, ax = plt.subplots(figsize=(9.4, 5.2), dpi=200)

    # Shade the two conditions whose comparison is the point of the design.
    ax.axvspan(0.9, 1.1, color="#e8f0fe", zorder=0)
    ax.axvspan(2.9, 3.1, color="#fce8e6", zorder=0)

    x = range(4)
    for name, filename, colour in MODELS:
        acc = load_mode_accuracy(filename)
        ax.plot(x, acc, marker="o", markersize=8, linewidth=2.6,
                color=colour, label=name, zorder=3)
        for xi, yi in zip(x, acc):
            ax.annotate(f"{yi:.1f}", (xi, yi), textcoords="offset points",
                        xytext=(0, 11), ha="center", fontsize=9.5,
                        color=colour, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels(MODE_LABELS, fontsize=9.5, color="#3c4043")
    ax.set_ylim(44, 90)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.set_ylabel("Accuracy (%)", fontsize=11, color="#3c4043")
    ax.set_title(
        "Relevant world knowledge helps — irrelevant knowledge in the identical format does not",
        fontsize=12.5, color="#202124", pad=26, loc="left", fontweight="bold",
    )
    ax.text(
        0.0, 1.035,
        "7,808 model responses per model · 1,952 question–image pairs × 4 prompting conditions",
        transform=ax.transAxes, fontsize=9.5, color="#80868b",
    )
    ax.legend(frameon=False, fontsize=10.5, loc="lower right", ncol=3,
              bbox_to_anchor=(1.0, -0.02))
    style_axes(ax)

    fig.text(0.125, 0.015,
             "Mode 2 and Mode 4 differ only in whether the injected knowledge is relevant — "
             "same format, same length, same position.",
             fontsize=9, color="#80868b")

    fig.tight_layout(rect=(0, 0.05, 1, 1))
    out = os.path.join(RESULTS_DIR, "fig_accuracy_by_mode.png")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def figure_gain_over_baseline():
    fig, ax = plt.subplots(figsize=(8.6, 4.6), dpi=200)

    gains = {}
    for name, filename, colour in MODELS:
        acc = load_mode_accuracy(filename)
        gains[name] = [acc[1] - acc[0], acc[2] - acc[0], acc[3] - acc[0]]

    n_models = len(MODELS)
    width = 0.26
    positions = range(len(GAIN_LABELS))

    for i, (name, _, colour) in enumerate(MODELS):
        offset = (i - (n_models - 1) / 2) * width
        xs = [p + offset for p in positions]
        bars = ax.bar(xs, gains[name], width=width, color=colour,
                      label=name, zorder=3)
        for rect, val in zip(bars, gains[name]):
            ax.annotate(f"{val:+.1f}", (rect.get_x() + rect.get_width() / 2, val),
                        textcoords="offset points",
                        xytext=(0, 7 if val >= 0 else -14), ha="center",
                        fontsize=9.5, color=colour, fontweight="bold")

    ax.axhline(0, color="#9aa0a6", linewidth=1)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(GAIN_LABELS, fontsize=9.5, color="#3c4043")
    ax.set_ylim(-6, 26)
    ax.yaxis.set_major_locator(MultipleLocator(5))
    ax.set_ylabel("Change vs. baseline (points)", fontsize=11, color="#3c4043")
    ax.set_title("What actually moves accuracy", fontsize=12.5,
                 color="#202124", pad=22, loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=10, loc="upper left")
    style_axes(ax)

    fig.tight_layout()
    out = os.path.join(RESULTS_DIR, "fig_gain_over_baseline.png")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


if __name__ == "__main__":
    for path in (figure_accuracy_by_mode(), figure_gain_over_baseline()):
        print("wrote", os.path.relpath(path, BASE_DIR))
