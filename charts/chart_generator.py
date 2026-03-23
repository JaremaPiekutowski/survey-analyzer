"""
Chart generation for survey reports.
Full label text (no truncation), large fonts, seaborn-inspired palettes.
"""

import logging
import textwrap
from io import BytesIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# === COLOR PALETTES ===
# Sequential (green, cold→warm like seaborn "crest")
SEQ_COLORS = ['#3B8686', '#4E9C81', '#6BAF76', '#8CBF69', '#B5CC5A', '#E0D94A']

# Diverging (Spectral-like)
DIV_CMAP = plt.cm.Spectral_r  # reversed so red=high, blue=low

# Categorical palette (professional, colorful)
CAT_PALETTE = ['#2E5B88', '#E07A3A', '#4DAF7C', '#C44E52', '#8B6DAF',
               '#E6B832', '#5DADE2', '#E67E22', '#27AE60']

PIE_PALETTE = ['#2E5B88', '#E07A3A', '#4DAF7C', '#C44E52', '#8B6DAF',
               '#E6B832', '#7FB3D8', '#F4A460', '#90C9A7']

COLORS = {
    'text': '#2D3436',
    'text_light': '#636E72',
    'grid': '#E0E4E8',
}

# Base font sizes (already 50% larger than typical defaults)
FONT_TITLE = 16
FONT_LABEL = 13
FONT_TICK = 12
FONT_ANNOT = 11
FONT_LEGEND = 11

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': FONT_TICK,
    'axes.titlesize': FONT_TITLE,
    'axes.titleweight': 'bold',
    'axes.labelsize': FONT_LABEL,
    'figure.dpi': 150,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.edgecolor': COLORS['grid'],
    'axes.grid': True,
    'grid.color': COLORS['grid'],
    'grid.alpha': 0.4,
})


def _wrap_title_text(text: str, max_chars_per_line: int = 64) -> str:
    """Wrap chart title so one long line does not stretch figure width (bbox tight)."""
    t = (text or "").strip()
    if not t:
        return ""
    return textwrap.fill(t, width=max_chars_per_line, break_long_words=False, replace_whitespace=False)


def _wrap_label(text: str, max_chars: int = 55) -> str:
    """Wrap long labels for axis display. Never truncate."""
    if len(text) <= max_chars:
        return text
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return '\n'.join(lines)


def _seq_color(val: float, vmin: float, vmax: float) -> tuple:
    """Map value to sequential green colormap (cold→warm)."""
    if pd.isna(val) or vmax == vmin:
        return COLORS['grid']
    norm = (val - vmin) / (vmax - vmin)
    norm = max(0, min(1, norm))
    # Green gradient: from cool teal to warm yellow-green
    r = 0.23 + norm * 0.65
    g = 0.53 + norm * 0.27
    b = 0.53 - norm * 0.40
    return (r, g, b)


def _div_color(val: float, vmin: float, vmax: float) -> tuple:
    """Map value to diverging Spectral colormap."""
    if pd.isna(val) or vmax == vmin:
        return COLORS['grid']
    norm = (val - vmin) / (vmax - vmin)
    return DIV_CMAP(norm)


def horizontal_bar_means(stats_df: pd.DataFrame, title: str = "",
                         scale_min: float = None, scale_max: float = None,
                         figsize: tuple = None, value_col: str = 'Średnia',
                         colormap: str = 'sequential',
                         row_spacing: float = 1.0, bar_height: float = 0.7) -> BytesIO:
    """Horizontal bar chart of means with full labels and color-coded bars."""
    df = stats_df.copy()
    n = len(df)

    if figsize is None:
        height = max(4, n * 0.55 * row_spacing + 2.5)
        figsize = (12, height)

    fig, ax = plt.subplots(figsize=figsize)

    labels = [_wrap_label(str(item)) for item in df['Item']]
    y_pos = np.arange(n)
    values = df[value_col].values

    vmin = scale_min if scale_min is not None else np.nanmin(values)
    vmax = scale_max if scale_max is not None else np.nanmax(values)

    color_fn = _div_color if colormap == 'diverging' else _seq_color
    bar_colors = [color_fn(v, vmin, vmax) for v in values]

    bars = ax.barh(y_pos, values, color=bar_colors, edgecolor='white', height=bar_height)

    # Value annotations
    x_margin = (vmax - vmin) * 0.02 if vmax > vmin else 0.1
    for bar, val, n_val in zip(bars, values, df.get('N', [None]*n)):
        if not pd.isna(val):
            txt = f'{val:.2f}'
            if n_val is not None and not pd.isna(n_val):
                txt += f'  (n={int(n_val)})'
            ax.text(bar.get_width() + x_margin, bar.get_y() + bar.get_height()/2,
                    txt, va='center', ha='left', fontsize=FONT_ANNOT, color=COLORS['text_light'])

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=FONT_TICK)
    ax.invert_yaxis()

    if scale_min is not None and scale_max is not None:
        ax.set_xlim(vmin - 0.1, vmax + (vmax - vmin) * 0.22)
    else:
        mx = np.nanmax(values) if len(values) > 0 else 1
        ax.set_xlim(0, mx * 1.3)

    if title:
        ax.set_title(title, fontsize=FONT_TITLE, fontweight='bold',
                      color=COLORS['text'], pad=15, loc='left')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', alpha=0.3)
    ax.grid(axis='y', visible=False)

    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


def pie_chart(freq_df: pd.DataFrame, title: str = "",
              figsize: tuple = (8, 6)) -> BytesIO:
    """Pie chart for few-category questions."""
    fig, ax = plt.subplots(figsize=figsize)
    labels = freq_df['Kategoria'].values
    sizes = freq_df['%'].values
    colors = PIE_PALETTE[:len(labels)]

    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, autopct='%1.1f%%',
        colors=colors, startangle=90, pctdistance=0.75,
        wedgeprops={'edgecolor': 'white', 'linewidth': 2}
    )
    for t in autotexts:
        t.set_fontsize(FONT_ANNOT)
        t.set_fontweight('bold')
        t.set_color('white')

    ax.legend(labels, loc='center left', bbox_to_anchor=(1.0, 0.5),
              fontsize=FONT_LEGEND, frameon=False)

    if title:
        ax.set_title(title, fontsize=FONT_TITLE, fontweight='bold',
                      color=COLORS['text'], pad=15)

    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


def frequency_bar(freq_df: pd.DataFrame, title: str = "",
                  horizontal: bool = True, figsize: tuple = None,
                  show_n: bool = True, row_spacing: float = 1.0,
                  bar_height: float = 0.7) -> BytesIO:
    """Bar chart for frequency distributions.
    row_spacing: multiply vertical spacing between categories (e.g. 1.1 for A2).
    """
    label_col = freq_df.columns[0]
    pct_col = '%' if '%' in freq_df.columns else '% wskazań'
    n_col = 'N' if 'N' in freq_df.columns else None

    df = freq_df.copy()
    n_items = len(df)

    if figsize is None:
        if horizontal:
            height = max(4, n_items * 0.55 * row_spacing + 2.5)
            figsize = (11, height)
        else:
            figsize = (max(8, n_items * 1.0 + 3), 6)

    fig, ax = plt.subplots(figsize=figsize)
    labels = [_wrap_label(str(l), 55) for l in df[label_col].values]
    values = df[pct_col].values

    # Color by value (sequential green)
    mx = max(values) if len(values) > 0 and max(values) > 0 else 1
    bar_colors = [_seq_color(v, 0, mx) for v in values]

    if horizontal:
        y_pos = np.arange(n_items)
        bars = ax.barh(y_pos, values, color=bar_colors, edgecolor='white', height=bar_height)
        for idx, (bar, val) in enumerate(zip(bars, values)):
            n_txt = ""
            if show_n and n_col and idx < len(df):
                n_txt = f"  (n={int(df[n_col].iloc[idx])})"
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                    f'{val:.1f}%{n_txt}', va='center', ha='left',
                    fontsize=FONT_ANNOT, color=COLORS['text_light'])
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=FONT_TICK)
        ax.invert_yaxis()
        ax.set_xlim(0, max(values) * 1.25 if max(values) > 0 else 100)
        ax.set_xlabel('%', fontsize=FONT_LABEL)
    else:
        x_pos = np.arange(n_items)
        bars = ax.bar(x_pos, values, color=bar_colors, edgecolor='white', width=0.7)
        for idx, (bar, val) in enumerate(zip(bars, values)):
            n_txt = ""
            if show_n and n_col and idx < len(df):
                n_txt = f"\n(n={int(df[n_col].iloc[idx])})"
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{val:.1f}%{n_txt}', ha='center', va='bottom',
                    fontsize=FONT_ANNOT, color=COLORS['text_light'])
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels, fontsize=FONT_TICK, rotation=30, ha='right')
        ax.set_ylabel('%', fontsize=FONT_LABEL)

    if title:
        ax.set_title(title, fontsize=FONT_TITLE, fontweight='bold',
                      color=COLORS['text'], pad=15, loc='left')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x' if horizontal else 'y', alpha=0.3)
    ax.grid(axis='y' if horizontal else 'x', visible=False)

    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


def grouped_bar_percent(pivot_df: pd.DataFrame, title: str = "",
                        category_col: str = "Kategoria",
                        figsize: tuple = None) -> BytesIO:
    """
    Grouped vertical bar chart: first column = category labels, rest = % per series (e.g. B5).
    """
    df = pivot_df.copy()
    if df.empty or category_col not in df.columns:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "Brak danych", ha="center", va="center")
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf

    group_cols = [c for c in df.columns if c != category_col]
    n_cats = len(df)
    n_groups = len(group_cols)
    if n_groups == 0:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "Brak danych", ha="center", va="center")
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf

    if figsize is None:
        width = max(10, n_cats * max(1.2, 0.35 * n_groups + 0.5))
        figsize = (width, 6.5)

    fig, ax = plt.subplots(figsize=figsize)
    x = np.arange(n_cats)
    bar_w = 0.8 / max(n_groups, 1)
    colors = CAT_PALETTE + PIE_PALETTE

    for i, gcol in enumerate(group_cols):
        vals = pd.to_numeric(df[gcol], errors="coerce").fillna(0.0).values
        offset = (i - (n_groups - 1) / 2.0) * bar_w
        ax.bar(
            x + offset,
            vals,
            bar_w,
            label=_wrap_label(str(gcol), 30),
            color=colors[i % len(colors)],
            edgecolor="white",
            linewidth=0.5,
        )

    cat_labels = [_wrap_label(str(t), 45) for t in df[category_col].values]
    ax.set_xticks(x)
    ax.set_xticklabels(cat_labels, fontsize=FONT_TICK, rotation=22, ha="right")
    ax.set_ylabel("%", fontsize=FONT_LABEL)
    ax.set_ylim(0, max(100, float(np.nanmax(df[group_cols].values)) * 1.15) if n_cats else 100)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=FONT_LEGEND - 1, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.grid(axis="x", visible=False)

    if title:
        ax.set_title(title, fontsize=FONT_TITLE, fontweight="bold",
                     color=COLORS["text"], pad=15, loc="left")

    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def grouped_bar_two_groups(
    df: pd.DataFrame,
    title: str = "",
    category_col: str = "Kategoria",
    value_cols: tuple[str, str] | None = None,
    n_cols: tuple[str, str] | None = None,
    legend_labels: tuple[str, str] | None = None,
    ylabel: str = "%",
    figsize: tuple = None,
    bar_labels: bool = True,
    horizontal: bool = False,
) -> BytesIO:
    """
    Grouped bar chart: two series (np. % Świeccy vs Duchowni).
    horizontal=False: słupki pionowe (kategorie na osi X).
    horizontal=True: słupki poziome (czytelne przy wielu długich etykietach, np. B8a).
    n_cols: optional (col_N_group1, col_N_group2) — etykiety jak frequency_bar: % i (n=…).
    """
    if df.empty or category_col not in df.columns:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "Brak danych", ha="center", va="center")
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf

    cols = [c for c in df.columns if c != category_col]
    if value_cols is not None:
        gcols = [value_cols[0], value_cols[1]]
    else:
        gcols = cols[:2]
    if len(gcols) < 2:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "Brak danych", ha="center", va="center")
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf

    leg = legend_labels if legend_labels else (gcols[0], gcols[1])

    n_cats = len(df)
    n_groups = 2
    colors = [CAT_PALETTE[0], CAT_PALETTE[1]]

    if horizontal:
        if figsize is None:
            height = max(12, n_cats * 0.72 + 4.5)
            figsize = (14, height)
        fig, ax = plt.subplots(figsize=figsize)
        y = np.arange(n_cats)
        bar_h = 0.8 / max(n_groups, 1)
        cat_labels = [_wrap_label(str(t), 55) for t in df[category_col].values]
        xmax = float(np.nanmax(df[gcols].values)) if n_cats else 0.0
        xlim_hi = max(100, xmax * 1.18) if ylabel == "%" else max(10, xmax * 1.18)
        xlim_hi *= 1.12

        for i, gcol in enumerate(gcols):
            vals = pd.to_numeric(df[gcol], errors="coerce").fillna(0.0).values
            offset = (i - (n_groups - 1) / 2.0) * bar_h
            rects = ax.barh(
                y + offset,
                vals,
                bar_h,
                label=_wrap_label(str(leg[i]), 30),
                color=colors[i % len(colors)],
                edgecolor="white",
                linewidth=0.5,
            )
            if bar_labels:
                n_series = None
                if n_cols is not None and n_cols[i] in df.columns:
                    n_series = df[n_cols[i]]
                for j, rect in enumerate(rects):
                    val = vals[j]
                    pct_sym = "%" if ylabel == "%" else ""
                    txt = f"{val:.1f}{pct_sym}"
                    if n_series is not None:
                        nv = n_series.iloc[j]
                        if pd.notna(nv):
                            txt += f"  (n={int(nv)})"
                    xend = rect.get_width()
                    yc = rect.get_y() + rect.get_height() / 2
                    pad = xlim_hi * 0.008
                    ax.text(
                        xend + pad, yc, txt,
                        va="center", ha="left", fontsize=FONT_ANNOT - 1,
                        color=COLORS["text_light"],
                    )

        ax.set_yticks(y)
        ax.set_yticklabels(cat_labels, fontsize=FONT_TICK)
        ax.invert_yaxis()
        ax.set_xlabel(ylabel, fontsize=FONT_LABEL)
        ax.set_xlim(0, xlim_hi)
        ax.legend(loc="lower right", fontsize=FONT_LEGEND, frameon=True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="x", alpha=0.3)
        ax.grid(axis="y", visible=False)
        if title:
            ax.set_title(title, fontsize=FONT_TITLE, fontweight="bold",
                         color=COLORS["text"], pad=15, loc="left")
        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf

    if figsize is None:
        width = max(10, n_cats * max(1.2, 0.35 * n_groups + 0.5))
        height = max(7.0, 5.0 + min(n_cats, 20) * 0.12)
        figsize = (width, height)

    fig, ax = plt.subplots(figsize=figsize)
    x = np.arange(n_cats)
    bar_w = 0.8 / max(n_groups, 1)

    for i, gcol in enumerate(gcols):
        vals = pd.to_numeric(df[gcol], errors="coerce").fillna(0.0).values
        offset = (i - (n_groups - 1) / 2.0) * bar_w
        rects = ax.bar(
            x + offset,
            vals,
            bar_w,
            label=_wrap_label(str(leg[i]), 30),
            color=colors[i % len(colors)],
            edgecolor="white",
            linewidth=0.5,
        )
        if bar_labels:
            n_series = None
            if n_cols is not None and n_cols[i] in df.columns:
                n_series = df[n_cols[i]]
            for j, rect in enumerate(rects):
                val = vals[j]
                pct_sym = "%" if ylabel == "%" else ""
                txt = f"{val:.1f}{pct_sym}"
                if n_series is not None:
                    nv = n_series.iloc[j]
                    if pd.notna(nv):
                        txt += f"\n(n={int(nv)})"
                ax.annotate(
                    txt,
                    xy=(rect.get_x() + rect.get_width() / 2, rect.get_height()),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=FONT_ANNOT - 1,
                    color=COLORS["text_light"],
                )

    cat_labels = [_wrap_label(str(t), 45) for t in df[category_col].values]
    ax.set_xticks(x)
    ax.set_xticklabels(cat_labels, fontsize=FONT_TICK, rotation=22, ha="right")
    ax.set_ylabel(ylabel, fontsize=FONT_LABEL)
    ymax = float(np.nanmax(df[gcols].values)) if n_cats else 0.0
    y_top = max(100, ymax * 1.28) if ylabel == "%" else max(10, ymax * 1.28)
    ax.set_ylim(0, y_top)
    ax.legend(loc="upper left", fontsize=FONT_LEGEND, frameon=True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.grid(axis="x", visible=False)

    if title:
        ax.set_title(title, fontsize=FONT_TITLE, fontweight="bold",
                     color=COLORS["text"], pad=15, loc="left")

    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def stacked_bar_100(freq_pivot_df: pd.DataFrame, title: str = "",
                    figsize: tuple = None, max_legend_items: int = 12) -> BytesIO:
    """
    100% stacked bar chart for cross-tabulated frequencies.
    freq_pivot_df: rows = response categories, columns = demographic groups, values = %.
    Each column sums to 100. One bar per demographic group.
    """
    df = freq_pivot_df.fillna(0)
    n_groups = len(df.columns)
    n_cats = len(df.index)

    if figsize is None:
        width = max(8, n_groups * 1.2 + 2)
        figsize = (width, 6)

    fig, ax = plt.subplots(figsize=figsize)
    x_pos = np.arange(n_groups)
    bar_width = 0.7

    colors = CAT_PALETTE + PIE_PALETTE
    bottom = np.zeros(n_groups)

    for i, (cat_label, row) in enumerate(df.iterrows()):
        vals = row.values
        color = colors[i % len(colors)]
        ax.bar(x_pos, vals, bar_width, bottom=bottom, label=_wrap_label(str(cat_label), 40),
               color=color, edgecolor='white', linewidth=0.5)
        bottom += vals

    ax.set_xticks(x_pos)
    ax.set_xticklabels([_wrap_label(str(c), 25) for c in df.columns],
                       fontsize=FONT_TICK, rotation=25, ha='right')
    ax.set_ylabel('%', fontsize=FONT_LABEL)
    ax.set_ylim(0, 100)
    ax.set_xlim(-0.5, n_groups - 0.5)

    if n_cats <= max_legend_items:
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=FONT_LEGEND - 1,
                  frameon=False)
    else:
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=FONT_LEGEND - 2,
                  frameon=False, ncol=min(2, (n_cats + 5) // 6))

    if title:
        ax.set_title(title, fontsize=FONT_TITLE, fontweight='bold',
                     color=COLORS['text'], pad=15, loc='left')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3)
    ax.grid(axis='x', visible=False)

    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


def comparison_bar(stats_df1: pd.DataFrame, stats_df2: pd.DataFrame,
                   label1: str = "Świeccy", label2: str = "Duchowni",
                   title: str = "", value_col: str = 'Średnia',
                   scale_min: float = None, scale_max: float = None,
                   figsize: tuple = None, sort_by_mean: bool = True,
                   font_scale: float = 1.0,
                   title_wrap_chars: int = 64) -> BytesIO:
    """Side-by-side horizontal bar chart comparing two groups (value + n jak w horizontal_bar_means)."""
    fs = float(font_scale) if font_scale and font_scale > 0 else 1.0
    ft_title = FONT_TITLE * fs
    ft_tick = FONT_TICK * fs
    ft_annot = FONT_ANNOT * fs
    ft_leg = FONT_LEGEND * fs
    m1 = stats_df1[['Item', value_col]].copy()
    m1 = m1.rename(columns={value_col: f'{value_col}_1'})
    m1['N_1'] = stats_df1['N'] if 'N' in stats_df1.columns else np.nan
    m2 = stats_df2[['Item', value_col]].copy()
    m2 = m2.rename(columns={value_col: f'{value_col}_2'})
    m2['N_2'] = stats_df2['N'] if 'N' in stats_df2.columns else np.nan
    merged = m1.merge(m2, on='Item', how='outer')
    k1, k2 = f'{value_col}_1', f'{value_col}_2'
    if sort_by_mean and len(merged) > 0:
        sort_key = merged[[k1, k2]].mean(axis=1).fillna(
            merged[k1].fillna(merged[k2])
        )
        merged = merged.iloc[np.argsort(-sort_key.values)].reset_index(drop=True)
    n = len(merged)
    if figsize is None:
        height = max(5, n * 0.72 + 3.2)
        figsize = (12, height)

    fig, ax = plt.subplots(figsize=figsize)
    labels = [_wrap_label(str(item)) for item in merged['Item']]
    y_pos = np.arange(n)
    bh = 0.35

    v1 = merged[k1].values
    v2 = merged[k2].values
    n1 = merged['N_1'].values
    n2 = merged['N_2'].values

    bars1 = ax.barh(y_pos - bh/2, v1, bh, label=label1, color=CAT_PALETTE[0], edgecolor='white')
    bars2 = ax.barh(y_pos + bh/2, v2, bh, label=label2, color=CAT_PALETTE[1], edgecolor='white')

    if scale_min is not None and scale_max is not None:
        vmin, vmax = float(scale_min), float(scale_max)
    else:
        concat = np.concatenate([v1, v2])
        fin = concat[np.isfinite(concat)]
        if len(fin) == 0:
            vmin, vmax = 0.0, 1.0
        else:
            vmin, vmax = float(np.min(fin)), float(np.max(fin))
    x_margin = (vmax - vmin) * 0.02 if vmax > vmin else 0.1

    for i in range(n):
        b1, b2 = bars1[i], bars2[i]
        if not pd.isna(v1[i]):
            txt = f'{v1[i]:.2f}'
            if not pd.isna(n1[i]):
                txt += f'  (n={int(n1[i])})'
            ax.text(
                b1.get_width() + x_margin, b1.get_y() + b1.get_height() / 2,
                txt, va='center', ha='left', fontsize=ft_annot, color=COLORS['text_light'],
            )
        if not pd.isna(v2[i]):
            txt = f'{v2[i]:.2f}'
            if not pd.isna(n2[i]):
                txt += f'  (n={int(n2[i])})'
            ax.text(
                b2.get_width() + x_margin, b2.get_y() + b2.get_height() / 2,
                txt, va='center', ha='left', fontsize=ft_annot, color=COLORS['text_light'],
            )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=ft_tick)
    ax.invert_yaxis()
    ax.legend(loc='lower right', frameon=True, fontsize=ft_leg)

    if scale_min is not None and scale_max is not None:
        ax.set_xlim(scale_min - 0.1, scale_max + (scale_max - scale_min) * 0.32)
    else:
        mx = np.nanmax(np.concatenate([v1, v2])) if n else 1.0
        ax.set_xlim(0, mx * 1.45)

    title_wrapped = ""
    if title:
        title_wrapped = _wrap_title_text(title, max_chars_per_line=title_wrap_chars)
        n_title_lines = max(1, title_wrapped.count("\n") + 1)
        title_pad = 12 + 6 * (n_title_lines - 1)
        ax.set_title(title_wrapped, fontsize=ft_title, fontweight='bold',
                     color=COLORS['text'], pad=title_pad, loc='left')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', alpha=0.3)
    ax.grid(axis='y', visible=False)

    plt.tight_layout()
    if title_wrapped and "\n" in title_wrapped:
        fig.subplots_adjust(top=min(0.97, 0.88 + 0.018 * title_wrapped.count("\n")))

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf
