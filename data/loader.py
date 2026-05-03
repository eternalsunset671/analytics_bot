import warnings

import pandas as pd

DATE_PARSE_THRESHOLD = 0.7


def load_file(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, encoding="utf-8")
    return _infer_types(df)


def _infer_types(df: pd.DataFrame) -> pd.DataFrame:
    """Авто-приведение типов: даты для object-столбцов + convert_dtypes() для всего остального."""
    for col in df.select_dtypes(include="object").columns:
        non_null = df[col].notna().sum()
        if non_null == 0:
            continue
        sample = df[col].dropna().astype(str).head(50)
        if not sample.str.contains(r"\d", regex=True).any():
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(df[col], errors="coerce")
        except Exception:
            continue
        if parsed.notna().sum() / non_null >= DATE_PARSE_THRESHOLD:
            df[col] = parsed

    return df.convert_dtypes()
