"""
Statistical computations for survey data.
Handles weighted means, medians, frequencies, cross-tabulations, and significance tests.
"""

import logging
import re
from collections import defaultdict
from typing import Optional

import pandas as pd
import numpy as np
from scipy import stats

from core.data_loader import QuestionDef, QT_LIKERT, QT_NUMERIC_SCALE
from core.report_ordering import sort_categories_for_merge_list

logger = logging.getLogger(__name__)


def largest_remainder_integers(counts: np.ndarray, target_total: int) -> np.ndarray:
    """
    Round nonnegative floats to integers summing to target_total (largest remainder).
    """
    counts = np.asarray(counts, dtype=float)
    counts = np.maximum(counts, 0.0)
    n = len(counts)
    if n == 0:
        return np.zeros(0, dtype=int)
    s = counts.sum()
    if s <= 0 or target_total <= 0:
        return np.zeros(n, dtype=int)
    scaled = counts / s * float(target_total)
    floored = np.floor(scaled)
    rem = int(round(target_total - floored.sum()))
    frac = scaled - floored
    order = np.argsort(-frac)
    res = floored.astype(int)
    for i in range(rem):
        res[order[i % n]] += 1
    return res


def weighted_mean(values: pd.Series, weights: Optional[pd.Series] = None) -> float:
    """Compute weighted or unweighted mean, ignoring NaN."""
    valid = values.dropna()
    if len(valid) == 0:
        return np.nan
    if weights is not None:
        w = weights.loc[valid.index].fillna(1.0)
        return np.average(valid.values, weights=w.values)
    return valid.mean()


def weighted_median(values: pd.Series, weights: Optional[pd.Series] = None) -> float:
    """Compute weighted or unweighted median, ignoring NaN."""
    valid = values.dropna()
    if len(valid) == 0:
        return np.nan
    if weights is None:
        return valid.median()
    
    w = weights.loc[valid.index].fillna(1.0)
    sorted_idx = valid.argsort()
    sorted_vals = valid.values[sorted_idx]
    sorted_weights = w.values[sorted_idx]
    cumsum = np.cumsum(sorted_weights)
    cutoff = cumsum[-1] / 2.0
    return float(sorted_vals[cumsum >= cutoff][0])


def weighted_std(values: pd.Series, weights: Optional[pd.Series] = None) -> float:
    """Compute weighted standard deviation."""
    valid = values.dropna()
    if len(valid) <= 1:
        return np.nan
    if weights is None:
        return valid.std()
    
    w = weights.loc[valid.index].fillna(1.0)
    avg = np.average(valid.values, weights=w.values)
    variance = np.average((valid.values - avg) ** 2, weights=w.values)
    return np.sqrt(variance)


def descriptive_stats(data: pd.DataFrame, weights: Optional[pd.Series] = None) -> pd.DataFrame:
    """
    Compute descriptive statistics for all numeric columns.
    Returns DataFrame with columns: N, Mean, Median, Std, Min, Max
    """
    rows = []
    for col in data.columns:
        if col.startswith('_'):
            continue
        series = pd.to_numeric(data[col], errors='coerce')
        valid = series.dropna()
        n = len(valid)
        
        w = weights if weights is not None else None
        
        rows.append({
            'Item': col,
            'N': int(n),
            'Średnia': round(weighted_mean(series, w), 2),
            'Mediana': round(weighted_median(series, w), 2),
            'Odch. std.': round(weighted_std(series, w), 2),
            'Min': valid.min() if n > 0 else np.nan,
            'Max': valid.max() if n > 0 else np.nan,
        })
    
    return pd.DataFrame(rows)


def frequency_table(series: pd.Series, weights: Optional[pd.Series] = None,
                    sort_by_count: bool = False) -> pd.DataFrame:
    """
    Compute frequency table for categorical data.
    Returns DataFrame with columns: Kategoria, N, %
    """
    from core.report_ordering import normalize_categorical_series

    s = normalize_categorical_series(series)
    valid = s.dropna()
    valid = valid[valid.astype(str).str.strip() != '']

    if weights is not None:
        w = weights.loc[valid.index].fillna(1.0)
        freq = valid.groupby(valid).apply(lambda x: w.loc[x.index].sum())
        total = float(w.loc[valid.index].sum())
        target_n = int(round(total))
    else:
        freq = valid.value_counts(sort=False)
        total = len(valid)
        target_n = int(total)

    if sort_by_count:
        freq = freq.sort_values(ascending=False)

    cats = freq.index.tolist()
    raw = np.asarray(freq.values, dtype=float)
    n_int = largest_remainder_integers(raw, target_n)
    pct_vals = (raw / total * 100) if total > 0 else np.zeros(len(raw))

    return pd.DataFrame({
        'Kategoria': cats,
        'N': n_int,
        '%': np.round(pct_vals, 1),
    }).reset_index(drop=True)


def multi_single_choice_frequency_pivot(
    df: pd.DataFrame,
    question,
    weights: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Same answer scale across several columns (e.g. B5: Matki, Ojca, Dziadków).
    Returns a wide table: Kategoria + one column per sub-question with %.
    """
    from core.report_ordering import order_frequency_dataframe

    col_labels = question.column_labels or [""] * len(question.columns)
    freqs = []
    for cidx in question.columns:
        col_name = df.columns[cidx]
        freq = frequency_table(df[col_name], weights)
        freq = order_frequency_dataframe(freq, question)
        freqs.append(freq)

    all_cats: list[str] = []
    seen: set[str] = set()
    for fr in freqs:
        for c in fr["Kategoria"].astype(str):
            if c not in seen:
                seen.add(c)
                all_cats.append(c)

    synth = pd.DataFrame({"Kategoria": all_cats, "%": [0.0] * len(all_cats)})
    synth = order_frequency_dataframe(synth, question)
    ordered_cats = synth["Kategoria"].tolist()

    maps_pct: list[dict] = []
    for fr in freqs:
        maps_pct.append(dict(zip(fr["Kategoria"].astype(str), fr["%"])))

    rows = []
    for cat in ordered_cats:
        row: dict = {"Kategoria": cat}
        for mi, lbl in enumerate(col_labels):
            lbl_clean = str(lbl).strip() or f"Kolumna {mi + 1}"
            row[lbl_clean] = round(float(maps_pct[mi].get(cat, 0.0)), 1)
        rows.append(row)
    return pd.DataFrame(rows)


def multiple_choice_table(data: pd.DataFrame, weights: Optional[pd.Series] = None) -> pd.DataFrame:
    """
    Compute frequency table for multiple choice (MENTIONED/NOT MENTIONED).
    Each column is one option. Returns % of respondents who mentioned each.
    """
    rows = []
    n_total = len(data)

    if weights is not None:
        total_w = float(weights.sum())
        target_n = int(round(total_w))
    else:
        total_w = float(n_total) if n_total else 0.0
        target_n = n_total

    for col in data.columns:
        if col.startswith('_'):
            continue
        series = data[col]

        if weights is not None:
            mentioned_w = weights[series == 1].sum()
            pct = (mentioned_w / total_w * 100) if total_w > 0 else 0
            n_raw = float(mentioned_w)
        else:
            n_raw = float((series == 1).sum())
            pct = (n_raw / n_total * 100) if n_total > 0 else 0

        rows.append({
            'Opcja': col,
            '_n_raw': n_raw,
            '% wskazań': round(pct, 1),
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        n_int = largest_remainder_integers(df['_n_raw'].values, target_n)
        df['N'] = n_int
        df = df.drop(columns=['_n_raw'])
        df = df[['Opcja', 'N', '% wskazań']]
    return df


def yes_no_matrix_table(
    df: pd.DataFrame,
    question,
    weight_col: Optional[str],
    weights: Optional[pd.Series],
) -> pd.DataFrame:
    """
    E3/E4 style: % Tak per named column + wiersz „Inne (jakie?)” z pierwszej kolumny
    otwartej (Tak/Nie), gdy są co najmniej dwie kolumny otwarte; w przeciwnym razie
    (legacy) % z niepustym tekstem w pojedynczej kolumnie otwartej.
    """
    from core.data_loader import get_numeric_data, parse_yes_no_cell

    data = get_numeric_data(df, question, weight_col)
    w = data.pop('_weight') if '_weight' in data.columns else weights
    if w is None:
        w = pd.Series(1.0, index=data.index)

    total_w = float(w.sum())
    target_n = int(round(total_w))
    rows = []

    for col in data.columns:
        if col.startswith('_'):
            continue
        series = data[col]
        mask_tak = series == 1.0
        raw = float(w[mask_tak].sum())
        pct = (raw / total_w * 100) if total_w > 0 else 0.0
        rows.append({
            'Opcja': col,
            '_n_raw': raw,
            '% wskazań': round(pct, 1),
        })

    oec = question.open_ended_columns or []
    if oec:
        if len(oec) >= 2:
            yn_idx = oec[0]
            if yn_idx < len(df.columns):
                yn_series = df[df.columns[yn_idx]].apply(parse_yes_no_cell)
                mask_tak_inne = yn_series == 1.0
                raw_inne = float(w[mask_tak_inne].sum())
                pct_inne = (raw_inne / total_w * 100) if total_w > 0 else 0.0
                rows.append({
                    'Opcja': 'Inne (jakie?)',
                    '_n_raw': raw_inne,
                    '% wskazań': round(pct_inne, 1),
                })
        else:
            mask_inne = pd.Series(False, index=df.index)
            idx = oec[0]
            if idx < len(df.columns):
                coln = df.columns[idx]
                txt = df[coln].apply(lambda x: '' if pd.isna(x) else str(x).strip())
                mask_inne = (txt != '') & (txt.str.lower() != 'nan') & (txt != '-')
            raw_inne = float(w[mask_inne].sum())
            pct_inne = (raw_inne / total_w * 100) if total_w > 0 else 0.0
            rows.append({
                'Opcja': 'Inne (jakie?)',
                '_n_raw': raw_inne,
                '% wskazań': round(pct_inne, 1),
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    n_int = largest_remainder_integers(out['_n_raw'].values, target_n)
    out['N'] = n_int
    out = out.drop(columns=['_n_raw'])
    return out[['Opcja', 'N', '% wskazań']]


def open_ended_other_text_table(
    df: pd.DataFrame,
    question,
    weight_col: Optional[str],
    weights: Optional[pd.Series],
    top_n: int = 25,
) -> pd.DataFrame:
    """
    Najczęstsze odpowiedzi tekstowe w drugiej (i kolejnych) kolumnie otwartej,
    wśród respondentów z Tak w pierwszej kolumnie otwartej i niepustym tekście.
    """
    from core.data_loader import parse_yes_no_cell

    oec = question.open_ended_columns or []
    if len(oec) < 2:
        return pd.DataFrame()

    yn_idx, txt_idx = oec[0], oec[1]
    if yn_idx >= len(df.columns) or txt_idx >= len(df.columns):
        return pd.DataFrame()

    w = weights
    if weight_col and weight_col in df.columns:
        w = pd.to_numeric(df[weight_col], errors='coerce').fillna(1.0)
    if w is None:
        w = pd.Series(1.0, index=df.index)

    yn_series = df[df.columns[yn_idx]].apply(parse_yes_no_cell)
    mask_tak = yn_series == 1.0
    txt_series = df[df.columns[txt_idx]].apply(
        lambda x: '' if pd.isna(x) else str(x).strip()
    )
    mask_txt = (txt_series != '') & (txt_series.str.lower() != 'nan') & (txt_series != '-')
    use = mask_tak & mask_txt
    if not use.any():
        return pd.DataFrame()

    tok_w: dict[str, float] = defaultdict(float)
    for idx in df.index[use]:
        t = txt_series.loc[idx].strip()
        parts = re.split(r'[,;\n]+', t)
        parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            parts = [t]
        wv = float(w.loc[idx])
        seen: set[str] = set()
        for p in parts:
            key = p[:500]
            if not key or key in seen:
                continue
            seen.add(key)
            tok_w[key] += wv

    if not tok_w:
        return pd.DataFrame()

    tot_mentions = sum(tok_w.values())
    sorted_items = sorted(tok_w.items(), key=lambda x: -x[1])[:top_n]
    rows = []
    for label, raw in sorted_items:
        pct = (raw / tot_mentions * 100) if tot_mentions > 0 else 0.0
        rows.append({
            'Opcja': label,
            '_n_raw': raw,
            '% wskazań': round(pct, 1),
        })

    out = pd.DataFrame(rows)
    target_n = int(round(tot_mentions))
    n_int = largest_remainder_integers(out['_n_raw'].values, target_n)
    out['N'] = n_int
    out = out.drop(columns=['_n_raw'])
    return out[['Opcja', 'N', '% wskazań']]


def cross_tab_means(data_col: pd.Series, group_col: pd.Series,
                    weights: Optional[pd.Series] = None) -> pd.DataFrame:
    """
    Cross-tabulation: mean of data_col by categories of group_col.
    """
    numeric = pd.to_numeric(data_col, errors='coerce')
    valid_mask = numeric.notna() & group_col.notna()
    numeric = numeric[valid_mask]
    groups = group_col[valid_mask]
    
    rows = []
    for cat in sorted(groups.unique(), key=str):
        mask = groups == cat
        vals = numeric[mask]
        w = weights[valid_mask][mask] if weights is not None else None
        
        rows.append({
            'Kategoria': cat,
            'N': int(len(vals)),
            'Średnia': round(weighted_mean(vals, w), 2),
            'Mediana': round(weighted_median(vals, w), 2),
            'Odch. std.': round(weighted_std(vals, w), 2),
        })
    
    return pd.DataFrame(rows)


def cross_tab_frequencies(data_col: pd.Series, group_col: pd.Series,
                          weights: Optional[pd.Series] = None) -> pd.DataFrame:
    """
    Cross-tabulation: frequency distribution of data_col by group_col categories.
    Returns pivot table: rows = data categories, columns = group categories, values = %.
    """
    from core.report_ordering import normalize_categorical_series

    data_col = normalize_categorical_series(data_col)
    valid_mask = data_col.notna() & group_col.notna()
    data_valid = data_col[valid_mask].astype(str)
    group_valid = group_col[valid_mask].astype(str)
    
    if weights is not None:
        w = weights[valid_mask]
        ct = pd.crosstab(data_valid, group_valid, values=w, aggfunc='sum')
    else:
        ct = pd.crosstab(data_valid, group_valid)
    
    # Convert to percentages (column-wise), avoid division by zero
    col_sums = ct.sum(axis=0)
    col_sums = col_sums.replace(0, np.nan)
    ct_pct = ct.div(col_sums, axis=1) * 100
    ct_pct = ct_pct.round(1).fillna(0)
    
    return ct_pct


def chi_square_test(data_col: pd.Series, group_col: pd.Series,
                    weights: Optional[pd.Series] = None) -> dict:
    """
    Chi-square test of independence between two categorical variables.
    Returns dict with test name, statistic, p_value.
    """
    from core.report_ordering import normalize_categorical_series

    data_col = normalize_categorical_series(data_col)
    valid_mask = data_col.notna() & group_col.notna()
    data_valid = data_col[valid_mask].astype(str).str.strip()
    group_valid = group_col[valid_mask].astype(str).str.strip()
    non_empty = (data_valid != '') & (group_valid != '')
    data_valid = data_valid[non_empty]
    group_valid = group_valid[non_empty]

    if len(data_valid) < 5:
        return {'test': 'chi2', 'statistic': np.nan, 'p_value': np.nan}

    if weights is not None:
        w = weights.loc[data_valid.index].fillna(1.0)
        contingency = pd.crosstab(data_valid, group_valid, values=w, aggfunc='sum').fillna(0)
    else:
        contingency = pd.crosstab(data_valid, group_valid)

    if contingency.shape[0] < 2 or contingency.shape[1] < 2:
        return {'test': 'chi2', 'statistic': np.nan, 'p_value': np.nan}

    try:
        chi2, p, dof, expected = stats.chi2_contingency(contingency)
        return {'test': 'chi2', 'statistic': round(float(chi2), 2), 'p_value': round(float(p), 4)}
    except ValueError:
        return {'test': 'chi2', 'statistic': np.nan, 'p_value': np.nan}


def test_group_differences(data_col: pd.Series, group_col: pd.Series,
                           test_type: str = 'auto') -> dict:
    """
    Test for statistically significant differences between groups.
    Returns dict with test name, statistic, p-value.
    """
    numeric = pd.to_numeric(data_col, errors='coerce')
    valid_mask = numeric.notna() & group_col.notna()
    
    if valid_mask.sum() < 5:
        return {'test': 'insufficient_data', 'statistic': np.nan, 'p_value': np.nan}
    
    numeric = numeric[valid_mask]
    groups = group_col[valid_mask]
    unique_groups = groups.unique()
    
    if len(unique_groups) < 2:
        return {'test': 'single_group', 'statistic': np.nan, 'p_value': np.nan}
    
    group_data = [numeric[groups == g].values for g in unique_groups]
    
    if len(unique_groups) == 2:
        # t-test or Mann-Whitney
        if test_type == 'auto':
            # Use Mann-Whitney for ordinal (Likert) data
            stat, p = stats.mannwhitneyu(group_data[0], group_data[1], alternative='two-sided')
            return {'test': 'Mann-Whitney U', 'statistic': round(stat, 2), 'p_value': round(p, 4)}
        elif test_type == 'ttest':
            stat, p = stats.ttest_ind(group_data[0], group_data[1])
            return {'test': 't-test', 'statistic': round(stat, 2), 'p_value': round(p, 4)}
    
    # 3+ groups: Kruskal-Wallis
    try:
        stat, p = stats.kruskal(*group_data)
        return {'test': 'Kruskal-Wallis', 'statistic': round(stat, 2), 'p_value': round(p, 4)}
    except Exception:
        return {'test': 'error', 'statistic': np.nan, 'p_value': np.nan}


def correlation_matrix(df: pd.DataFrame, method: str = 'spearman') -> pd.DataFrame:
    """
    Compute correlation matrix for numeric columns.
    Spearman is default (better for ordinal/Likert data).
    """
    numeric_df = df.apply(pd.to_numeric, errors='coerce')
    numeric_df = numeric_df.dropna(axis=1, how='all')
    
    if method == 'spearman':
        corr = numeric_df.corr(method='spearman')
    else:
        corr = numeric_df.corr(method='pearson')
    
    return corr.round(3)


def scale_value_to_category_label(val, q: QuestionDef):
    """Map one numeric scale/Likert value to a stable category label string."""
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return np.nan
    v = float(val)
    if q.question_type == QT_LIKERT:
        iv = int(v) if abs(v - int(v)) < 1e-9 else None
        if iv is not None and q.scale_labels:
            if iv in q.scale_labels:
                return str(q.scale_labels[iv])
            for k, lbl in q.scale_labels.items():
                if int(k) == iv:
                    return str(lbl)
        if iv is not None:
            return str(iv)
        return str(v)
    if q.question_type == QT_NUMERIC_SCALE:
        if abs(v - int(v)) < 1e-9:
            return str(int(v))
        return str(v)
    return str(v)


def scale_series_to_category_labels(series: pd.Series, q: QuestionDef) -> pd.Series:
    return series.apply(lambda x: scale_value_to_category_label(x, q))


def ordered_scale_categories_for_compare(q: QuestionDef) -> list[str]:
    """Ordered category labels for scale/Likert (excluding special_values for Likert)."""
    if q.question_type not in (QT_NUMERIC_SCALE, QT_LIKERT):
        return []
    smin = q.scale_min if q.scale_min is not None else 0
    smax = q.scale_max if q.scale_max is not None else 10
    out: list[str] = []
    for v in range(smin, smax + 1):
        if q.question_type == QT_LIKERT and q.special_values and v in q.special_values:
            continue
        lbl = scale_value_to_category_label(float(v), q)
        if lbl is not None and not (isinstance(lbl, float) and np.isnan(lbl)):
            out.append(lbl)
    return out


def order_categories_for_merge(
    freq1: pd.DataFrame,
    freq2: pd.DataFrame,
    q: QuestionDef,
) -> Optional[list[str]]:
    """Build ordered category list for merge_two_frequency_tables."""
    if q.question_type in (QT_NUMERIC_SCALE, QT_LIKERT):
        return ordered_scale_categories_for_compare(q)
    cats1 = freq1['Kategoria'].astype(str).tolist()
    cats2 = freq2['Kategoria'].astype(str).tolist()
    seen: set[str] = set()
    ordered: list[str] = []
    for c in cats1 + cats2:
        if c not in seen:
            ordered.append(c)
            seen.add(c)
    return sort_categories_for_merge_list(ordered, q)


def merge_two_frequency_tables(
    freq1: pd.DataFrame,
    freq2: pd.DataFrame,
    label1: str,
    label2: str,
    ordered_categories: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Merge two frequency tables (Kategoria, N, %) from two independent samples.
    """
    d1 = {str(r['Kategoria']): (int(r['N']), float(r['%'])) for _, r in freq1.iterrows()}
    d2 = {str(r['Kategoria']): (int(r['N']), float(r['%'])) for _, r in freq2.iterrows()}
    all_cats = set(d1) | set(d2)
    ordered: list[str] = []
    if ordered_categories:
        seen: set[str] = set()
        for c in ordered_categories:
            cs = str(c)
            if cs in all_cats and cs not in seen:
                ordered.append(cs)
                seen.add(cs)
        for c in all_cats:
            if c not in seen:
                ordered.append(c)
                seen.add(c)
    else:
        seen = set()
        for c in freq1['Kategoria'].astype(str).tolist() + freq2['Kategoria'].astype(str).tolist():
            if c not in seen and c in all_cats:
                ordered.append(c)
                seen.add(c)
        for c in all_cats:
            if c not in seen:
                ordered.append(c)

    rows = []
    for c in ordered:
        n1, p1 = d1.get(c, (0, 0.0))
        n2, p2 = d2.get(c, (0, 0.0))
        rows.append({
            'Kategoria': c,
            f'N ({label1})': n1,
            f'% ({label1})': p1,
            f'N ({label2})': n2,
            f'% ({label2})': p2,
        })
    return pd.DataFrame(rows)


def merge_two_option_tables(
    tbl1: pd.DataFrame,
    tbl2: pd.DataFrame,
    label1: str,
    label2: str,
    q: QuestionDef,
) -> pd.DataFrame:
    """Merge multiple-choice or yes/no matrix tables (Opcja, N, % wskazań)."""
    from core.report_ordering import order_multiple_choice_dataframe

    tbl1 = order_multiple_choice_dataframe(tbl1.copy(), q)
    d2 = {str(r['Opcja']): (int(r['N']), float(r['% wskazań'])) for _, r in tbl2.iterrows()}
    rows = []
    seen2: set[str] = set()
    for _, r in tbl1.iterrows():
        op = str(r['Opcja'])
        seen2.add(op)
        n1, p1 = int(r['N']), float(r['% wskazań'])
        n2, p2 = d2.get(op, (0, 0.0))
        rows.append({
            'Opcja': op,
            f'N ({label1})': n1,
            f'% ({label1})': p1,
            f'N ({label2})': n2,
            f'% ({label2})': p2,
        })
    for _, r in tbl2.iterrows():
        op = str(r['Opcja'])
        if op not in seen2:
            n2, p2 = int(r['N']), float(r['% wskazań'])
            rows.append({
                'Opcja': op,
                f'N ({label1})': 0,
                f'% ({label1})': 0.0,
                f'N ({label2})': n2,
                f'% ({label2})': p2,
            })
    return pd.DataFrame(rows)
