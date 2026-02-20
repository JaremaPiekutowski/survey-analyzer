"""
Statistical computations for survey data.
Handles weighted means, medians, frequencies, cross-tabulations, and significance tests.
"""

import logging
from typing import Optional

import pandas as pd
import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


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
            'N': n,
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
    valid = series.dropna()
    valid = valid[valid.astype(str).str.strip() != '']
    
    if weights is not None:
        w = weights.loc[valid.index].fillna(1.0)
        freq = valid.groupby(valid).apply(lambda x: w.loc[x.index].sum())
        total = w.loc[valid.index].sum()
    else:
        freq = valid.value_counts(sort=False)
        total = len(valid)
    
    if sort_by_count:
        freq = freq.sort_values(ascending=False)
    
    result = pd.DataFrame({
        'Kategoria': freq.index,
        'N': freq.values,
        '%': (freq.values / total * 100).round(1) if total > 0 else 0,
    }).reset_index(drop=True)
    
    return result


def multiple_choice_table(data: pd.DataFrame, weights: Optional[pd.Series] = None) -> pd.DataFrame:
    """
    Compute frequency table for multiple choice (MENTIONED/NOT MENTIONED).
    Each column is one option. Returns % of respondents who mentioned each.
    """
    rows = []
    n_total = len(data)
    
    for col in data.columns:
        if col.startswith('_'):
            continue
        series = data[col]
        
        if weights is not None:
            mentioned_w = weights[series == 1].sum()
            total_w = weights.sum()
            pct = (mentioned_w / total_w * 100) if total_w > 0 else 0
            n_mentioned = (series == 1).sum()
        else:
            n_mentioned = (series == 1).sum()
            pct = (n_mentioned / n_total * 100) if n_total > 0 else 0
        
        rows.append({
            'Opcja': col,
            'N': n_mentioned,
            '% wskazań': round(pct, 1),
        })
    
    return pd.DataFrame(rows).sort_values('% wskazań', ascending=False).reset_index(drop=True)


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
            'N': len(vals),
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
