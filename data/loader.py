import pandas as pd


def load_file(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path, encoding="utf-8")
