"""
Chart generation for survey reports.
Full label text (no truncation), large fonts, seaborn-inspired palettes.
"""

import logging
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
                         colormap: str = 'sequential') -> BytesIO:
    """Horizontal bar chart of means with full labels and color-coded bars."""
    df = stats_df.copy()
    n = len(df)

    if figsize is None:
        height = max(4, n * 0.55 + 2.5)
        figsize = (12, height)

    fig, ax = plt.subplots(figsize=figsize)

    labels = [_wrap_label(str(item)) for item in df['Item']]
    y_pos = np.arange(n)
    values = df[value_col].values

    vmin = scale_min if scale_min is not None else np.nanmin(values)
    vmax = scale_max if scale_max is not None else np.nanmax(values)

    color_fn = _div_color if colormap == 'diverging' else _seq_color
    bar_colors = [color_fn(v, vmin, vmax) for v in values]

    bars = ax.barh(y_pos, values, color=bar_colors, edgecolor='white', height=0.7)

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
                  show_n: bool = True) -> BytesIO:
    """Bar chart for frequency distributions."""
    label_col = freq_df.columns[0]
    pct_col = '%' if '%' in freq_df.columns else '% wskazań'
    n_col = 'N' if 'N' in freq_df.columns else None

    df = freq_df.copy()
    n_items = len(df)

    if figsize is None:
        if horizontal:
            height = max(4, n_items * 0.55 + 2.5)
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
        bars = ax.barh(y_pos, values, color=bar_colors, edgecolor='white', height=0.7)
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
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{val:.1f}%', ha='center', va='bottom',
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


def comparison_bar(stats_df1: pd.DataFrame, stats_df2: pd.DataFrame,
                   label1: str = "Świeccy", label2: str = "Duchowni",
                   title: str = "", value_col: str = 'Średnia',
                   scale_min: float = None, scale_max: float = None,
                   figsize: tuple = None) -> BytesIO:
    """Side-by-side horizontal bar chart comparing two groups."""
    merged = stats_df1[['Item', value_col]].merge(
        stats_df2[['Item', value_col]], on='Item', how='outer', suffixes=('_1', '_2'))
    n = len(merged)
    if figsize is None:
        height = max(5, n * 0.65 + 3)
        figsize = (12, height)

    fig, ax = plt.subplots(figsize=figsize)
    labels = [_wrap_label(str(item)) for item in merged['Item']]
    y_pos = np.arange(n)
    bh = 0.35

    v1 = merged[f'{value_col}_1'].values
    v2 = merged[f'{value_col}_2'].values

    ax.barh(y_pos - bh/2, v1, bh, label=label1, color=CAT_PALETTE[0], edgecolor='white')
    ax.barh(y_pos + bh/2, v2, bh, label=label2, color=CAT_PALETTE[1], edgecolor='white')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=FONT_TICK)
    ax.invert_yaxis()
    ax.legend(loc='lower right', frameon=True, fontsize=FONT_LEGEND)

    if scale_min is not None and scale_max is not None:
        ax.set_xlim(scale_min - 0.1, scale_max + (scale_max - scale_min) * 0.15)

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
