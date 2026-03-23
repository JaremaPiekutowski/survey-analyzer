"""
Display ordering for report tables and charts: Polish collation, tail categories,
per-question rules, section titles.
"""

from __future__ import annotations

import locale
import re
from typing import Optional

import numpy as np
import pandas as pd

from core.data_loader import QuestionDef

# --- Section titles ---

def format_section_title(q: QuestionDef) -> str:
    """Avoid 'B1a: B1a. Question text' — strip duplicate id prefix from label."""
    lid = (q.label or "").strip()
    qid = (q.id or "").strip()
    if not qid:
        return lid
    for pat in (rf"^{re.escape(qid)}\.\s*", rf"^{re.escape(qid)}:\s*"):
        lid = re.sub(pat, "", lid, flags=re.IGNORECASE)
    return f"{qid}: {lid}".strip()


# --- Polish collation ---

def _try_set_polish_locale() -> bool:
    for loc in ("pl_PL.UTF-8", "pl_PL", "Polish"):
        try:
            locale.setlocale(locale.LC_COLLATE, loc)
            return True
        except (locale.Error, OSError):
            continue
    return False


_POLISH_LOCALE_OK = _try_set_polish_locale()


def polish_sort_key(text: str) -> str:
    if not _POLISH_LOCALE_OK:
        return text.lower()
    try:
        return locale.strxfrm(str(text))
    except Exception:
        return str(text).lower()


# --- Category normalization ---

def normalize_categorical_series(series: pd.Series) -> pd.Series:
    """Map '-' to 'Brak odpowiedzi'; strip whitespace; fix known typos in labels."""
    out = series.copy()
    mask_na = out.isna()
    as_str = out.astype(str).str.strip()
    as_str = as_str.replace({"nan": "", "None": ""})
    as_str = as_str.replace("-", "Brak odpowiedzi")
    as_str = as_str.str.replace(
        r"(?i)dziecezjalny", "diecezjalny", regex=True
    )
    out = as_str
    out = out.where(~mask_na, np.nan)
    out = out.where(as_str.str.lower() != "", np.nan)
    return out


# --- Tail categories (order at end) ---

# Pytania, w których „odmowa odpowiedzi” ma być na samym końcu (po „braku odpowiedzi”).
# Jawna lista — dopisz/usuń id, jeśli w kwestionariuszu pojawią się nowe (bez regexów).
ODMOWA_LAST_QUESTION_IDS = frozenset({
    "B5", "B6", "B7", "B8", "B8a", "B9", "B9a",
})


def _qid_odmowa_last(q_id: Optional[str]) -> bool:
    return bool(q_id) and q_id in ODMOWA_LAST_QUESTION_IDS


def _is_inne_tail_label(s: str) -> bool:
    """True for 'Inne (jakie?)' style options; not '... i inne nowoczesne ...'."""
    sl = (s or "").strip().lower()
    if "inne (jakie" in sl:
        return True
    if sl == "inne":
        return True
    if re.match(r"^inne\s*[\?,:;\(]", sl):
        return True
    return False


def _tail_rank(label: str, q_id: Optional[str] = None) -> Optional[int]:
    """
    Kolejność ogólna na końcu: żadne z powyższych → inne → trudno/nie wiem → odmowa → brak.
    Dla id z ODMOWA_LAST_QUESTION_IDS: brak przed odmową (odmowa na samym końcu).
    """
    s = (label or "").strip().lower()
    if not s:
        return None
    odmowa_last = _qid_odmowa_last(q_id)
    if "żadne z powyższych" in s or "żadne z powyzszych" in s:
        return 0
    if _is_inne_tail_label(s):
        return 1
    if "trudno powiedzieć" in s or "trudno powiedziec" in s:
        return 2
    if "nie wiem" in s and "trudno" in s:
        return 2
    if "nie wiem" in s:
        return 2
    if "brak odpowiedzi" in s or s in ("brak", "-"):
        return 3 if odmowa_last else 4
    if "odmowa" in s:
        return 4 if odmowa_last else 3
    return None


def _is_tak(s: str) -> bool:
    t = (s or "").strip().lower()
    return t in ("tak", "t") or t.startswith("tak")


def _is_nie(s: str) -> bool:
    t = (s or "").strip().lower()
    return t in ("nie", "n") or t.startswith("nie")


def split_tail_categories(
    labels: list[str],
    q_id: Optional[str] = None,
) -> tuple[list[str], list[str]]:
    """Return (main_labels, tail_labels) in tail order."""
    main, tail = [], []
    for lb in labels:
        if _tail_rank(lb, q_id) is not None:
            tail.append(lb)
        else:
            main.append(lb)
    tail.sort(key=lambda x: (_tail_rank(x, q_id) or 99, polish_sort_key(x)))
    return main, tail


def order_labels_with_tail(
    labels: list[str],
    main_order: list[str],
    q_id: Optional[str] = None,
) -> list[str]:
    """Append any labels not in main_order at end (before tail)."""
    main_set = set(main_order)
    extra = [x for x in labels if x not in main_set and _tail_rank(x, q_id) is None]
    tail = [x for x in labels if _tail_rank(x, q_id) is not None]
    tail.sort(key=lambda x: (_tail_rank(x, q_id) or 99, polish_sort_key(x)))
    seen = set()
    out = []
    for x in main_order + extra:
        if x in seen:
            continue
        if x in labels:
            out.append(x)
            seen.add(x)
    for x in labels:
        if x not in seen and x not in tail:
            out.append(x)
            seen.add(x)
    out.extend(t for t in tail if t in labels)
    return out


def sort_categories_for_merge_list(cats: list[str], q: QuestionDef) -> list[str]:
    """Kolejność kategorii w scalonej tabeli: główne wg pierwszego wystąpienia, ogon wg _tail_rank."""
    qid = q.id
    if q.category_order:
        return order_labels_with_tail(cats, q.category_order, qid=qid)
    main: list[str] = []
    seen: set[str] = set()
    for c in cats:
        if _tail_rank(c, qid) is None and c not in seen:
            main.append(c)
            seen.add(c)
    tail: list[str] = []
    seen_t: set[str] = set()
    for c in cats:
        if _tail_rank(c, qid) is not None and c not in seen_t:
            tail.append(c)
            seen_t.add(c)
    tail.sort(key=lambda x: (_tail_rank(x, qid) or 99, polish_sort_key(x)))
    return main + tail


# --- Built-in order lists (exact strings may vary slightly in data) ---

def _match_order(
    categories: list[str],
    preferred: list[str],
) -> list[str]:
    """Order categories following preferred list; fuzzy contains match."""
    cats = list(categories)
    out = []
    used = set()
    for pref in preferred:
        for c in cats:
            if c in used:
                continue
            if pref.lower() in c.lower() or c.lower() in pref.lower():
                out.append(c)
                used.add(c)
                break
    for c in cats:
        if c not in used:
            out.append(c)
    return out


# Per-question rules: (mode, data) where data is list for custom or None
BUILTIN_ORDER: dict[str, tuple[str, Optional[list[str]]]] = {
    # M10 świeccy: wieś first, then cities small → large
    "M10": ("custom", [
        "wieś",
        "do 20 tys.",
        "20–199 tys.",
        "200–499 tys.",
        "powyżej 500 tys.",
    ]),
    "M8": ("custom", [
        "do 2500 zł",
        "2501–3500 zł",
        "3501–4500 zł",
        "4501–5500 zł",
        "powyżej 5500 zł",
    ]),
    "M9": ("custom", [
        "pieniędzy wystarcza tylko na podstawowe potrzeby",
        "żyjemy bardzo oszczędnie, aby odłożyć na poważniejsze zakupy",
        "żyjemy oszczędnie i dzięki temu wystarcza na wszystko",
        "wystarcza na wszystko bez specjalnych wyrzeczeń",
        "wystarcza na wszystko i jeszcze oszczędzamy",
    ]),
    "M5": ("custom", [
        "kawalerem",
        "panną",
        "partnerem",
        "wolnym związku",
        "żonaty",
        "zamężna",
        "rozwiedziony",
        "separacji",
        "wdowcem",
        "wdową",
    ]),
    "M3": ("custom", [
        "nie mam formalnego wykształcenia",
        "podstawowe",
        "gimnazjalne",
        "zasadnicze zawodowe",
        "średnie ogólnokształcące",
        "średnie",
        "pomaturalne",
        "licencjat",
        "inżynier",
        "magisterskie",
        "podyplomowe",
        "mba",
        "doktorat",
        "odmowa",
    ]),
    "M4": ("custom", [
        "uczę się",
        "studiuję",
        "emeryt",
        "rencist",
        "urlopie macierzyńskim",
        "nie pracuję",
        "zajmuję się domem",
        "bezrobotny",
        "bezrobotna",
        "dorywczo",
        "stałą pracę",
        "inna sytuacja",
        "odmowa",
    ]),
    "M6": ("custom", [
        "kawalerem",
        "panną",
        "żonaty",
        "zamężna",
        "partnerem",
        "wolnym związku",
        "rozwiedziony",
        "separacji",
        "wdowcem",
        "wdową",
        "odmowa",
    ]),
    "B7": ("custom", [
        "zdecydowanie zmalał",
        "raczej zmalał",
        "nie zmienił",
        "raczej wzrósł",
        "zdecydowanie wzrósł",
    ]),
    "D3": ("custom", [
        "na pewno nie wziął",
        "raczej nie wziął",
        "trudno powiedzieć",
        "raczej wziął",
        "na pewno wziął",
    ]),
    "D4": ("custom", [
        "lewica",
        "koalicja obywatelska",
        "polska 2050",
        "psl",
        "konfederacja",
        "prawo i sprawiedliwość",
        "nie mam zdania",
        "nie zagłosował",
        "odmowa",
    ]),
    "B5": ("custom", [
        "bardzo religijn",
        "raczej religijn",
        "w ogóle niereligijn",
        "ateist",
        "nie wiem",
        "trudno powiedzieć",
        "odmowa",
        "religijn",
    ]),
    "B2": ("custom", [
        "religijną",
        "raczej religijną",
        "raczej niereligijną",
        "niereligijną",
        "zdecydowanym ateist",
        "zdecydowaną ateist",
        "nie wiem",
        "trudno powiedzieć",
        "odmowa odpowiedzi",
        "odmowa",
    ]),
    "B3": ("custom", [
        "codziennie",
        "częściej niż raz w tygodniu",
        "co najmniej raz w miesiącu",
        "raz na tydzień",
        "okazji szczególnych świąt",
        "jeszcze rzadziej",
        "nigdy",
        "nie wiem",
        "trudno powiedzieć",
        "odmowa",
    ]),
    "B3a": ("custom", [
        "kilka razy dziennie",
        "codziennie",
        "częściej niż raz w tygodniu",
        "co najmniej raz w miesiącu",
        "raz na tydzień",
        "okazji szczególnych świąt",
        "jeszcze rzadziej",
        "nigdy",
        "nie wiem",
        "trudno powiedzieć",
        "odmowa",
    ]),
    "E2": ("custom", [
        "codziennie lub prawie codziennie",
        "kilka razy w tygodniu",
        "kilka razy w miesiącu",
        "raz w miesiącu",
        "rzadziej niż raz w miesiącu",
        "raz w tygodniu",
        "nie wiem",
        "trudno powiedzieć",
        "brak odpowiedzi",
    ]),
}

# Likert / scale: średnia malejąco (bez jawnej listy w YAML)
_MEAN_DESC_IDS = frozenset({
    "A1", "A1a", "A2", "A3a", "A3b", "C2", "D1a", "D1b", "D2a", "D2b", "D2c",
    "E5a", "E5b", "E5c", "D5a", "D5b",
})


def resolve_order_spec(q: QuestionDef) -> tuple[str, Optional[list[str]]]:
    if q.category_order:
        return ("custom", q.category_order)
    if q.sort_mode and q.sort_mode != "auto":
        return (q.sort_mode, None)
    if q.id in BUILTIN_ORDER:
        return BUILTIN_ORDER[q.id]
    if q.id in _MEAN_DESC_IDS:
        return ("by_mean_desc", None)
    return ("auto", None)


def order_frequency_dataframe(
    df: pd.DataFrame,
    q: QuestionDef,
    label_col: str = "Kategoria",
) -> pd.DataFrame:
    """Reorder rows of a frequency table (Kategoria, N, %)."""
    if df.empty or label_col not in df.columns:
        return df
    mode, preferred = resolve_order_spec(q)
    cats = df[label_col].astype(str).tolist()
    if mode == "polish_alpha" or q.id == "M11":
        order = sorted(range(len(cats)), key=lambda i: polish_sort_key(cats[i]))
        return df.iloc[order].reset_index(drop=True)
    if mode == "custom" and preferred:
        new_order = _match_order(cats, preferred)
        idx_map = {c: i for i, c in enumerate(cats)}
        seq = [idx_map[c] for c in new_order if c in idx_map]
        seen = set(seq)
        seq.extend(i for i in range(len(cats)) if i not in seen)
        return df.iloc[seq].reset_index(drop=True)
    if mode == "by_frequency_asc":
        return df.sort_values("%", ascending=True, na_position="last").reset_index(drop=True)
    if mode == "by_frequency_desc":
        main, tail = split_tail_categories(cats, q.id)
        tail_set = set(tail)
        main_df = df[~df[label_col].isin(tail_set)].copy()
        tail_df = df[df[label_col].isin(tail_set)].copy()
        main_df = main_df.sort_values("%", ascending=False, na_position="last")
        tail_df["_rk"] = tail_df[label_col].map(
            lambda s: _tail_rank(str(s), q.id) or 99
        )
        tail_df = tail_df.sort_values("_rk").drop(columns=["_rk"])
        return pd.concat([main_df, tail_df], ignore_index=True)
    # auto: by % desc, tail last
    pct_col = "%" if "%" in df.columns else None
    if pct_col is None:
        return df
    main, tail = split_tail_categories(cats, q.id)
    tail_set = set(tail)
    main_df = df[~df[label_col].isin(tail_set)].copy()
    tail_df = df[df[label_col].isin(tail_set)].copy()
    main_df = main_df.sort_values(pct_col, ascending=False, na_position="last")
    tail_df["_rk"] = tail_df[label_col].map(
        lambda s: _tail_rank(str(s), q.id) or 99
    )
    tail_df = tail_df.sort_values("_rk").drop(columns=["_rk"])
    return pd.concat([main_df, tail_df], ignore_index=True)


def _pin_nie_bylo_before_odmowa(df: pd.DataFrame, label_col: str = "Opcja") -> pd.DataFrame:
    """B8/B8a: 'Nie było żadnych' przed 'Odmowa odpowiedzi'."""
    mask_nie = df[label_col].astype(str).str.lower().str.contains("nie było", na=False)
    mask_odm = df[label_col].astype(str).str.lower().str.contains("odmowa", na=False)
    if not mask_nie.any() or not mask_odm.any():
        return df
    rest = df[~mask_nie & ~mask_odm]
    row_nie = df[mask_nie].iloc[:1]
    row_odm = df[mask_odm].iloc[:1]
    return pd.concat([rest, row_nie, row_odm], ignore_index=True)


def order_multiple_choice_dataframe(df: pd.DataFrame, q: QuestionDef) -> pd.DataFrame:
    """Reorder rows for multiple-choice (% wskazań)."""
    if df.empty or "Opcja" not in df.columns:
        return df
    label_col = "Opcja"
    cats = df[label_col].astype(str).tolist()
    mode, preferred = resolve_order_spec(q)
    if mode == "custom" and preferred:
        new_order = _match_order(cats, preferred)
        idx_map = {c: i for i, c in enumerate(cats)}
        seq = [idx_map[c] for c in new_order if c in idx_map]
        seen = set(seq)
        seq.extend(i for i in range(len(cats)) if i not in seen)
        out = df.iloc[seq].reset_index(drop=True)
        if q.id in ("B8", "B8a"):
            out = _pin_nie_bylo_before_odmowa(out)
        return out
    if mode == "polish_alpha" or q.id == "M11":
        order = sorted(range(len(cats)), key=lambda i: polish_sort_key(cats[i]))
        out = df.iloc[order].reset_index(drop=True)
        if q.id in ("B8", "B8a"):
            out = _pin_nie_bylo_before_odmowa(out)
        return out
    pct_col = "% wskazań" if "% wskazań" in df.columns else "%"
    main, tail = split_tail_categories(cats, q.id)
    tail_set = set(tail)
    main_df = df[~df[label_col].isin(tail_set)].copy()
    tail_df = df[df[label_col].isin(tail_set)].copy()
    main_df = main_df.sort_values(pct_col, ascending=False, na_position="last")
    tail_df["_rk"] = tail_df[label_col].map(
        lambda s: _tail_rank(str(s), q.id) or 99
    )
    tail_df = tail_df.sort_values("_rk").drop(columns=["_rk"])
    out = pd.concat([main_df, tail_df], ignore_index=True)
    if q.id in ("B8", "B8a"):
        out = _pin_nie_bylo_before_odmowa(out)
    return out


def order_descriptive_stats(df: pd.DataFrame, q: QuestionDef) -> pd.DataFrame:
    """Reorder Likert/scale rows by mean descending; tail items last."""
    if df.empty or "Item" not in df.columns or "Średnia" not in df.columns:
        return df
    mode, preferred = resolve_order_spec(q)
    items = df["Item"].astype(str).tolist()
    if mode == "polish_alpha" or q.id == "M11":
        order = sorted(range(len(items)), key=lambda i: polish_sort_key(items[i]))
        return df.iloc[order].reset_index(drop=True)
    if mode == "custom" and preferred:
        new_order = _match_order(items, preferred)
        idx_map = {c: i for i, c in enumerate(items)}
        seq = [idx_map[c] for c in new_order if c in idx_map]
        seen = set(seq)
        seq.extend(i for i in range(len(items)) if i not in seen)
        return df.iloc[seq].reset_index(drop=True)
    main, tail = split_tail_categories(items, q.id)
    tail_set = set(tail)
    main_df = df[~df["Item"].isin(tail_set)].copy()
    tail_df = df[df["Item"].isin(tail_set)].copy()
    main_df = main_df.sort_values("Średnia", ascending=False, na_position="last")
    tail_df["_rk"] = tail_df["Item"].map(
        lambda s: _tail_rank(str(s), q.id) or 99
    )
    tail_df = tail_df.sort_values("_rk").drop(columns=["_rk"])
    return pd.concat([main_df, tail_df], ignore_index=True)


def order_demo_category_rows(ct: pd.DataFrame, demo_q: QuestionDef) -> pd.DataFrame:
    """Reorder cross_tab_means rows (demographic groups)."""
    if ct.empty or "Kategoria" not in ct.columns:
        return ct
    cats = ct["Kategoria"].astype(str).tolist()
    if demo_q.id == "M11":
        order = sorted(range(len(cats)), key=lambda i: polish_sort_key(cats[i]))
        return ct.iloc[order].reset_index(drop=True)
    if demo_q.id == "M10":
        spec = BUILTIN_ORDER.get("M10")
        if spec and spec[1]:
            new_order = _match_order(cats, spec[1])
            idx_map = {c: i for i, c in enumerate(cats)}
            seq = [idx_map[c] for c in new_order if c in idx_map]
            seen = set(seq)
            seq.extend(i for i in range(len(cats)) if i not in seen)
            return ct.iloc[seq].reset_index(drop=True)
    return ct


def order_cross_tab_pivot(
    ct_pct: pd.DataFrame,
    q: QuestionDef,
) -> pd.DataFrame:
    """Reorder rows of percentage pivot (response categories)."""
    if ct_pct.empty:
        return ct_pct
    rows = ct_pct.index.astype(str).tolist()
    mode, preferred = resolve_order_spec(q)
    if mode == "polish_alpha" or q.id == "M11":
        order = sorted(rows, key=polish_sort_key)
        return ct_pct.reindex([r for r in order if r in ct_pct.index])
    if mode == "custom" and preferred:
        new_order = _match_order(rows, preferred)
        return ct_pct.reindex([r for r in new_order if r in ct_pct.index])
    means = ct_pct.mean(axis=1)
    if mode == "by_frequency_asc":
        ord_idx = means.sort_values(ascending=True).index
        return ct_pct.reindex(ord_idx)
    if mode == "by_frequency_desc":
        main = [r for r in rows if _tail_rank(r, q.id) is None]
        tail = [r for r in rows if _tail_rank(r, q.id) is not None]
        main_sorted = sorted(main, key=lambda r: -float(means.get(r, 0)))
        tail_sorted = sorted(
            tail, key=lambda r: (_tail_rank(r, q.id) or 99, polish_sort_key(r))
        )
        order = main_sorted + tail_sorted
        return ct_pct.reindex([r for r in order if r in ct_pct.index])
    # auto: średnia % w kolumnach jako przybliżenie częstości
    main = [r for r in rows if _tail_rank(r, q.id) is None]
    tail = [r for r in rows if _tail_rank(r, q.id) is not None]
    main_sorted = sorted(main, key=lambda r: -float(means.get(r, 0)))
    tail_sorted = sorted(
        tail, key=lambda r: (_tail_rank(r, q.id) or 99, polish_sort_key(r))
    )
    order = main_sorted + tail_sorted
    return ct_pct.reindex([r for r in order if r in ct_pct.index])


def order_cross_tab_columns_polish(
    ct_pct: pd.DataFrame,
    demo_q: QuestionDef,
) -> pd.DataFrame:
    """When breakdown dimension is M11, order columns (województwa) Polish."""
    if ct_pct.empty or demo_q.id != "M11":
        return ct_pct
    cols = list(ct_pct.columns)
    order = sorted(cols, key=polish_sort_key)
    return ct_pct[order]


def tak_nie_category_order(categories: list[str]) -> list[str]:
    """Tak, Nie, then tail."""
    tak, nie, rest = [], [], []
    for c in categories:
        cs = str(c).strip().lower()
        if _is_tak(cs):
            tak.append(c)
        elif _is_nie(cs):
            nie.append(c)
        else:
            rest.append(c)
    main, tail = split_tail_categories(rest, None)
    out = tak + nie + main
    tail.sort(key=lambda x: (_tail_rank(x, None) or 99, polish_sort_key(x)))
    out.extend(tail)
    return out
