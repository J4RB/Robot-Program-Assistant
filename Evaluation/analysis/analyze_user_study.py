from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import pandas as pd
import seaborn as sns

BASELINE_COLOR = "#466A8E"
PROPOSED_COLOR = "#D95F0E"


def parse_duration_to_seconds(value: object) -> float | None:
    """Parse hh:mm:ss values, accepting both ':' and '.' separators and DNF."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.upper() == "DNF":
        return None
    text = text.replace(".", ":")
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2})$", text)
    if not match:
        return None
    h, m, s = map(int, match.groups())
    return float(h * 3600 + m * 60 + s)


def normalize_task_label(value: object) -> str | None:
    """Normalize task identifiers like 4, T4, or 'Task 4' into 'T4'."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    if not match:
        return None
    task_num = int(match.group(1))
    if 1 <= task_num <= 11:
        return f"T{task_num}"
    return None


def normalize_participant_label(value: object) -> str | None:
    """Normalize participant names to the lowercased first name used in log folders."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.split()[0].lower()


def display_task_label(task_label: object) -> str | None:
    """Convert internal T1..T11 labels to report labels CT-1..CT-6 and MT-1..MT-5."""
    normalized = normalize_task_label(task_label)
    if normalized is None:
        return None
    task_num = int(normalized[1:])
    if task_num <= 6:
        return f"CT-{task_num}"
    return f"MT-{task_num - 6}"


def likert_to_numeric(series: pd.Series) -> pd.Series:
    mapping = {
        "strongly disagree": 1,
        "disagree": 2,
        "neutral": 3,
        "agree": 4,
        "strongly agree": 5,
    }
    normalized = series.astype("string").str.strip().str.lower()
    return normalized.map(mapping)


def divergent_likert_horizontal(
    items: list[tuple[str, pd.Series]],
    title: str,
    out_path: Path,
) -> None:
    """Create a horizontal divergent stacked bar chart for 5-point Likert data."""
    categories = [
        "Strongly disagree",
        "Disagree",
        "Neutral",
        "Agree",
        "Strongly agree",
    ]
    colors = {
        "Strongly disagree": "#D95F0E",
        "Disagree": "#F29E67",
        "Neutral": "#B8BFC5",
        "Agree": "#87A1B8",
        "Strongly agree": "#466A8E",
    }

    rows: list[dict[str, float | str]] = []
    for label, series in items:
        normalized = series.astype("string").str.strip().str.lower()
        counts = normalized.value_counts()
        total = int(counts.sum())
        row: dict[str, float | str] = {"item": label}
        for category in categories:
            row[category] = float(counts.get(category.lower(), 0)) / total if total else 0.0
        rows.append(row)

    plot_df = pd.DataFrame(rows)

    fig_h = max(3.8, 0.6 * len(plot_df) + 1.8)
    fig, ax = plt.subplots(figsize=(10.0, fig_h))

    y_positions = list(range(len(plot_df)))
    labels = plot_df["item"].tolist()

    max_abs = 0.0
    for i, row in plot_df.iterrows():
        sd = float(row["Strongly disagree"])
        d = float(row["Disagree"])
        n = float(row["Neutral"])
        a = float(row["Agree"])
        sa = float(row["Strongly agree"])

        n_half = n / 2.0
        left_total = sd + d + n_half
        right_total = sa + a + n_half
        max_abs = max(max_abs, left_total, right_total)

        # Left side: strongly disagree, disagree, half neutral.
        left_start = -(sd + d + n_half)
        segments_left = [
            ("Strongly disagree", sd),
            ("Disagree", d),
            ("Neutral", n_half),
        ]
        cursor = left_start
        for cat, width in segments_left:
            if width > 0:
                ax.barh(i, width, left=cursor, color=colors[cat], edgecolor="white", linewidth=0.7)
                if width >= 0.12 and cat != "Neutral":
                    ax.text(
                        cursor + width / 2,
                        i,
                        f"{int(round(width * 100))}%",
                        ha="center",
                        va="center",
                        fontsize=8.5,
                        fontweight="bold",
                        color="white" if cat in {"Strongly disagree", "Disagree"} else "black",
                    )
                cursor += width

        # Right side: half neutral, agree, strongly agree.
        right_start = 0.0
        segments_right = [
            ("Neutral", n_half),
            ("Agree", a),
            ("Strongly agree", sa),
        ]
        cursor = right_start
        for cat, width in segments_right:
            if width > 0:
                ax.barh(i, width, left=cursor, color=colors[cat], edgecolor="white", linewidth=0.7)
                if width >= 0.12 and cat != "Neutral":
                    ax.text(
                        cursor + width / 2,
                        i,
                        f"{int(round(width * 100))}%",
                        ha="center",
                        va="center",
                        fontsize=8.5,
                        fontweight="bold",
                        color="white" if cat in {"Agree", "Strongly agree"} else "black",
                    )
                cursor += width

            # Show one combined neutral percentage just right of the middle line.
            if n > 0:
                ax.text(
                    0.01,
                    i,
                    f"{int(round(n * 100))}%",
                    ha="left",
                    va="center",
                    fontsize=8.5,
                    fontweight="bold",
                    color="black",
                )

    # Center line and mirrored percentage scale.
    ax.axvline(0, color="#333333", linewidth=1.8)
    limit = max(0.5, min(1.0, max_abs + 0.08))
    ax.set_xlim(-limit, limit)
    ax.set_xticks([])
    ax.set_xticklabels([])
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title(title)

    legend_labels = ["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"]
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=colors[label], ec="white", lw=0.7) for label in legend_labels
    ]
    ax.legend(
        legend_handles,
        legend_labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=5,
        frameon=False,
        fontsize=8.5,
    )
    sns.despine(ax=ax, left=True, bottom=False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "Evaluation" / "data"
    out_dir = root / "report" / "media" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)

    correctness = pd.read_csv(data_dir / "respons-correctness.csv")
    timing = pd.read_csv(data_dir / "respons-time.csv")
    ai_use = pd.read_csv(data_dir / "respons-ai_use.csv")
    responses = pd.read_csv(data_dir / "respons.csv")

    # Column groups
    a_comp_cols = [c for c in correctness.columns if c.startswith("A:") and "Modification" not in c]
    a_mod_cols = [c for c in correctness.columns if c.startswith("A: Modification")]
    b_comp_cols = [c for c in correctness.columns if c.startswith("B:") and "Modification" not in c]
    b_mod_cols = [c for c in correctness.columns if c.startswith("B: Modification")]

    a_comp_time_cols = [c for c in timing.columns if c.startswith("A:") and "Modification" not in c]
    a_mod_time_cols = [c for c in timing.columns if c.startswith("A: Modification")]
    b_comp_time_cols = [c for c in timing.columns if c.startswith("B:") and "Modification" not in c]
    b_mod_time_cols = [c for c in timing.columns if c.startswith("B: Modification")]

    # Correctness summary
    def correctness_stats(cols: list[str]) -> dict[str, float | int | None]:
        numeric = correctness[cols].apply(pd.to_numeric, errors="coerce")
        nonmissing = int(numeric.notna().sum().sum())
        total = int(numeric.size)
        mean_completed_only = float(numeric.stack().mean()) if nonmissing > 0 else None
        # DNF-inclusive metric: treat missing (DNF) values as incorrect (0).
        mean_with_dnf_as_incorrect = float(numeric.fillna(0.0).to_numpy().mean()) if total > 0 else None
        return {
            "nonmissing": nonmissing,
            "total": total,
            "mean_completed_only": mean_completed_only,
            "mean_with_dnf_as_incorrect": mean_with_dnf_as_incorrect,
        }

    correctness_summary = {
        "A_comprehension": correctness_stats(a_comp_cols),
        "A_modification": correctness_stats(a_mod_cols),
        "B_comprehension": correctness_stats(b_comp_cols),
        "B_modification": correctness_stats(b_mod_cols),
    }

    # Timing summary
    def parse_time_frame(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.apply(lambda col: col.map(parse_duration_to_seconds))

    def phase_time_stats(cols: list[str]) -> dict[str, object]:
        parsed = parse_time_frame(timing[cols])
        per_participant_sum = parsed.sum(axis=1, min_count=1)
        return {
            "participant_sum_sec": [None if pd.isna(v) else float(v) for v in per_participant_sum],
            "mean_minutes": float(per_participant_sum.mean() / 60.0),
            "median_minutes": float(per_participant_sum.median() / 60.0),
            "completed_participants": int(per_participant_sum.notna().sum()),
            "task_completion_rate": float(parsed.notna().sum().sum() / parsed.size),
        }

    timing_summary = {
        "A_comprehension": phase_time_stats(a_comp_time_cols),
        "A_modification": phase_time_stats(a_mod_time_cols),
        "B_comprehension": phase_time_stats(b_comp_time_cols),
        "B_modification": phase_time_stats(b_mod_time_cols),
    }

    # AI usage (only recorded for B tasks)
    ai_task_cols = [c for c in ai_use.columns if c.startswith("B:")]
    ai_numeric = ai_use[ai_task_cols].apply(pd.to_numeric, errors="coerce")
    ai_usage_summary = {
        "overall_rate": float(ai_numeric.stack().mean()),
        "total_used": int(ai_numeric.sum().sum()),
        "total_possible": int(ai_numeric.size),
        "per_task_rate": {k: float(v) for k, v in ai_numeric.mean().to_dict().items()},
    }

    # Confidence comparison baseline vs proposed
    confidence_summary = {
        "comprehension_baseline_mean": float(
            likert_to_numeric(
                responses["I felt confident in my program comprehension when using the baseline approach. "]
            ).mean()
        ),
        "comprehension_proposed_mean": float(
            likert_to_numeric(
                responses["I felt confident in my program comprehension when using the proposed system. "]
            ).mean()
        ),
        "modification_baseline_mean": float(
            likert_to_numeric(
                responses["I felt confident in my program modifications when using the baseline approach. "]
            ).mean()
        ),
        "modification_proposed_mean": float(
            likert_to_numeric(
                responses["I felt confident in my program modifications when using the proposed system. "]
            ).mean()
        ),
    }

    summary = {
        "n_participants": int(len(responses)),
        "correctness": correctness_summary,
        "timing": timing_summary,
        "ai_use": ai_usage_summary,
        "confidence": confidence_summary,
    }

    # Assistant runtime logs (pre-extracted by extract_log_data.py).
    raw_sessions_path = data_dir / "assistant_logs_raw_sessions.csv"
    raw_embeddings_path = data_dir / "assistant_logs_raw_embeddings.csv"
    missing_inputs = [
        str(path.relative_to(root))
        for path in [raw_sessions_path, raw_embeddings_path]
        if not path.exists()
    ]
    if missing_inputs:
        missing_text = "\n".join(f"- {path}" for path in missing_inputs)
        raise FileNotFoundError(
            "Missing extracted assistant log files. Run Evaluation/analysis/extract_log_data.py first."
            f"\n{missing_text}"
        )

    logs_df = pd.read_csv(raw_sessions_path)
    embeddings_df = pd.read_csv(raw_embeddings_path)
    if not logs_df.empty:
        logs_df["program_context"] = logs_df["program_context"].astype(str).str.lower().eq("true")
        duration_stats = logs_df["duration_s"].describe()
        tool_stats = logs_df["tool_calls"].describe()
        all_embedding_ms = embeddings_df["embedding_time_ms"].astype(float) if not embeddings_df.empty else pd.Series(dtype=float)
        logs_summary = {
            "session_count": int(len(logs_df)),
            "duration_seconds": {
                "mean": float(duration_stats["mean"]),
                "median": float(duration_stats["50%"]),
                "q25": float(duration_stats["25%"]),
                "q75": float(duration_stats["75%"]),
                "min": float(duration_stats["min"]),
                "max": float(duration_stats["max"]),
            },
            "tool_calls": {
                "mean": float(tool_stats["mean"]),
                "median": float(tool_stats["50%"]),
                "min": float(tool_stats["min"]),
                "max": float(tool_stats["max"]),
                "distribution": {
                    str(int(k)): int(v)
                    for k, v in logs_df["tool_calls"].value_counts().sort_index().to_dict().items()
                },
            },
            "embedding_time_ms_per_call": {
                "mean": float(all_embedding_ms.mean()) if not all_embedding_ms.empty else None,
                "median": float(all_embedding_ms.median()) if not all_embedding_ms.empty else None,
                "n": int(len(all_embedding_ms)),
            },
            "program_context": {
                "true_count": int((logs_df["program_context"] == True).sum()),
                "false_count": int((logs_df["program_context"] == False).sum()),
                "duration_seconds_mean": {
                    "true": float(logs_df.loc[logs_df["program_context"] == True, "duration_s"].mean()),
                    "false": float(logs_df.loc[logs_df["program_context"] == False, "duration_s"].mean()),
                },
            },
        }
        summary["assistant_logs"] = logs_summary

        # Figure 12: Assistant latency by number of tool calls.
        fig, ax = plt.subplots(figsize=(8.2, 4.8))
        sns.boxplot(data=logs_df, x="tool_calls", y="duration_s", color="#B8BFC5", ax=ax)
        sns.stripplot(
            data=logs_df,
            x="tool_calls",
            y="duration_s",
            hue="program_context",
            palette={True: "#466A8E", False: "#D95F0E"},
            alpha=0.8,
            dodge=False,
            size=5,
            ax=ax,
        )
        ax.set_xlabel("Number of tool calls in a session")
        ax.set_ylabel("Assistant response time (seconds)")
        ax.set_title("Assistant latency vs. tool-call count")
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            label_map = {"False": "No context", "True": "Program context"}
            ax.legend(handles, [label_map.get(label, label) for label in labels], title="Query context")
        fig.tight_layout()
        fig.savefig(out_dir / "assistant_latency_by_tool_calls.png", dpi=300)
        plt.close(fig)

    # Plot style
    sns.set_theme(style="whitegrid")
    palette = {"Baseline (A)": BASELINE_COLOR, "Proposed (B)": PROPOSED_COLOR}

    def build_task_time_df() -> pd.DataFrame:
        a_task_cols = [c for c in timing.columns if c.startswith("A:")]
        b_task_cols = [c for c in timing.columns if c.startswith("B:")]
        b_ai_cols = [c for c in ai_use.columns if c.startswith("B:")]

        parsed_a = parse_time_frame(timing[a_task_cols])
        parsed_b = parse_time_frame(timing[b_task_cols])
        ai_b = ai_use[b_ai_cols].apply(pd.to_numeric, errors="coerce")

        rows: list[dict[str, object]] = []
        for idx in range(len(timing)):
            participant = timing.loc[idx, "Enter your name:"]

            for task_idx, col in enumerate(a_task_cols, start=1):
                sec = parsed_a.loc[idx, col]
                rows.append(
                    {
                        "participant": participant,
                        "condition": "Baseline (A)",
                        "task_index": task_idx,
                        "task_label": f"T{task_idx}",
                        "phase": "Comprehension" if task_idx <= 6 else "Modification",
                        "seconds": None if pd.isna(sec) else float(sec),
                        "minutes": None if pd.isna(sec) else float(sec / 60.0),
                        "completed": bool(pd.notna(sec)),
                        "ai_used": None,
                    }
                )

            for task_idx, col in enumerate(b_task_cols, start=1):
                sec = parsed_b.loc[idx, col]
                ai_val = ai_b.loc[idx, b_ai_cols[task_idx - 1]]
                rows.append(
                    {
                        "participant": participant,
                        "condition": "Proposed (B)",
                        "task_index": task_idx,
                        "task_label": f"T{task_idx}",
                        "phase": "Comprehension" if task_idx <= 6 else "Modification",
                        "seconds": None if pd.isna(sec) else float(sec),
                        "minutes": None if pd.isna(sec) else float(sec / 60.0),
                        "completed": bool(pd.notna(sec)),
                        "ai_used": None if pd.isna(ai_val) else bool(int(ai_val)),
                    }
                )

        return pd.DataFrame(rows)

    # Figure: Task-level timing by task order, split per phase.
    task_time_df = build_task_time_df()
    task_completed = task_time_df[task_time_df["completed"] == True].copy()

    # Manual styling control: lower this value to fade AI-split lines more.
    AI_SPLIT_ALPHA = 0.6
    phase_tasks = {
        "Comprehension": [f"T{i}" for i in range(1, 7)],
        "Modification": [f"T{i}" for i in range(7, 12)],
    }
    phase_display_tasks = {
        "Comprehension": [f"CT-{i}" for i in range(1, 7)],
        "Modification": [f"MT-{i}" for i in range(1, 6)],
    }
    phase_suffix = {"Comprehension": "comprehension", "Modification": "modification"}

    for phase_name, task_order in phase_tasks.items():
        phase_df = task_completed[task_completed["phase"] == phase_name].copy()
        phase_df["task_label"] = pd.Categorical(phase_df["task_label"], categories=task_order, ordered=True)
        phase_df["task_display"] = phase_df["task_label"].map(display_task_label)
        phase_df["task_display"] = pd.Categorical(
            phase_df["task_display"],
            categories=phase_display_tasks[phase_name],
            ordered=True,
        )

        mean_all = (
            phase_df.groupby(["condition", "task_display"], observed=True)["minutes"]
            .mean()
            .reset_index()
        )
        mean_b_split = (
            phase_df[phase_df["condition"] == "Proposed (B)"]
            .groupby(["task_display", "ai_used"], observed=True)["minutes"]
            .mean()
            .reset_index()
        )

        mean_a = mean_all[mean_all["condition"] == "Baseline (A)"]
        mean_b = mean_all[mean_all["condition"] == "Proposed (B)"]
        mean_b_ai = mean_b_split[mean_b_split["ai_used"] == True]
        mean_b_noai = mean_b_split[mean_b_split["ai_used"] == False]

        fig, ax = plt.subplots(figsize=(7.6, 4.8))
        ax.plot(
            mean_a["task_display"],
            mean_a["minutes"],
            marker="o",
            linewidth=2,
            color=BASELINE_COLOR,
            label="Baseline mean",
        )
        ax.plot(
            mean_b["task_display"],
            mean_b["minutes"],
            marker="o",
            linewidth=2,
            color=PROPOSED_COLOR,
            label="Proposed mean",
        )
        ax.plot(
            mean_b_ai["task_display"],
            mean_b_ai["minutes"],
            marker="o",
            linestyle=":",
            linewidth=1.8,
            color=PROPOSED_COLOR,
            alpha=AI_SPLIT_ALPHA,
            label="Proposed mean (AI used)",
        )
        ax.plot(
            mean_b_noai["task_display"],
            mean_b_noai["minutes"],
            marker="o",
            linestyle="--",
            linewidth=1.8,
            color=PROPOSED_COLOR,
            alpha=AI_SPLIT_ALPHA,
            label="Proposed mean (no AI)",
        )

        ax.set_title(f"Mean {phase_name.lower()} task time")
        ax.set_xlabel("Task")
        ax.set_ylabel("Task time (minutes)")
        ax.tick_params(axis="x", rotation=0)
        ax.legend(loc="upper right", fontsize=8.5, frameon=True)
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        fig.savefig(
            out_dir / f"time_by_task_order_with_ai_use_{phase_suffix[phase_name]}.png",
            dpi=300,
            bbox_inches="tight",
            pad_inches=0.08,
        )
        plt.close(fig)

    # Figure 2: AI usage rate per task in B
    ai_task_rates = (
        ai_numeric.mean().reset_index().rename(columns={"index": "task", 0: "usage_rate"})
    )
    ai_task_rates["task_short"] = [display_task_label(f"T{i+1}") for i in range(len(ai_task_rates))]
    group_colors = ["#87A1B8" if i < 6 else "#466A8E" for i in range(len(ai_task_rates))]
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    ax.bar(ai_task_rates["task_short"], ai_task_rates["usage_rate"], color=group_colors)
    ax.set_ylim(0, 1.0)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("Task")
    ax.set_ylabel("AI use rate (% of participants)")
    ax.set_title("AI assistant use in proposed condition (B)")
    ax.xaxis.grid(False)
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color="#87A1B8"),
        plt.Rectangle((0, 0), 1, 1, color="#466A8E"),
    ]
    ax.legend(legend_handles, ["Comprehension", "Modification"], title="Task group", loc="upper left")
    fig.tight_layout()
    fig.savefig(out_dir / "ai_use_rate_by_task.png", dpi=300)
    plt.close(fig)


    # Figure 3: Confidence baseline vs proposed
    conf_df = pd.DataFrame( 
        {
            "Outcome": ["Comprehension", "Comprehension", "Modification", "Modification"],
            "Condition": ["Baseline", "Proposed", "Baseline", "Proposed"],
            "Mean Likert": [
                confidence_summary["comprehension_baseline_mean"],
                confidence_summary["comprehension_proposed_mean"],
                confidence_summary["modification_baseline_mean"],
                confidence_summary["modification_proposed_mean"],
            ],
        }
    )
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    sns.barplot(
        data=conf_df,
        x="Outcome",
        y="Mean Likert",
        hue="Condition",
        palette={"Baseline": BASELINE_COLOR, "Proposed": PROPOSED_COLOR},
        ax=ax,
    )
    ax.set_ylim(1, 5)
    ax.set_ylabel("Mean confidence (1-5)")
    ax.set_xlabel("")
    ax.set_title("Self-reported confidence by condition")
    fig.tight_layout()
    fig.savefig(out_dir / "confidence_by_condition.png", dpi=300)
    plt.close(fig)

    # Figure: Post-study response comprehension quality (divergent stacked Likert)
    comprehension_items = [
        ("High quality", responses["The LLM-generated comprehension responses were of high quality. "]),
        ("Relevant to query", responses["The LLM-generated comprehension responses were relevant to my query. "]),
        ("Clear and understandable", responses["The LLM-generated comprehension responses were clear and understandable. "]),
        ("Factually correct", responses["The LLM-generated comprehension responses were factually correct. "]),
    ]
    divergent_likert_horizontal(
        items=comprehension_items,
        title="Post-study: response comprehension ratings",
        out_path=out_dir / "post_study_response_comprehension_diverging.png",
    )

    # Figure: Post-study response modification quality (divergent stacked Likert)
    modification_items = [
        ("High quality", responses["The LLM-generated modification suggestions were of high quality. "]),
        ("Relevant to task", responses["The LLM-generated modification suggestions were relevant to the modification task. "]),
        ("Clear and understandable", responses["The LLM-generated modification suggestions were clear and understandable. "]),
        ("Factually correct", responses["The LLM-generated modification suggestions were factually correct. "]),
    ]
    divergent_likert_horizontal(
        items=modification_items,
        title="Post-study: response modification ratings",
        out_path=out_dir / "post_study_response_modification_diverging.png",
    )

    # Figure: Post-study system usability (divergent stacked Likert)
    usability_items = [
        ("Easy to use", responses["The proposed system was easy to use. "]),
        ("Useful for tasks", responses["The proposed system was useful for robotic programming tasks. "]),
        ("Would use proposed system", responses["I would use the proposed system in my robotic programming work."]),
    ]
    divergent_likert_horizontal(
        items=usability_items,
        title="Post-study: system usability ratings",
        out_path=out_dir / "post_study_system_usability_diverging.png",
    )

    with open(data_dir / "results_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
