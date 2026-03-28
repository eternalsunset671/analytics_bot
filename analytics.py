import io
import textwrap
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_file(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path, encoding="utf-8")


def get_basic_stats(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    buf.write(f"Строк: {len(df)}, Столбцов: {len(df.columns)}\n")
    buf.write(f"Столбцы: {', '.join(df.columns.tolist())}\n\n")

    # Типы данных
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(include="object").columns.tolist()
    buf.write(f"Числовые столбцы ({len(numeric_cols)}): {', '.join(numeric_cols)}\n")
    buf.write(f"Категориальные столбцы ({len(cat_cols)}): {', '.join(cat_cols)}\n\n")

    # Пропуски
    missing = df.isnull().sum()
    missing = missing[missing > 0]
    if len(missing) > 0:
        buf.write("Пропуски:\n")
        for col, cnt in missing.items():
            pct = cnt / len(df) * 100
            buf.write(f"  {col}: {cnt} ({pct:.1f}%)\n")
    else:
        buf.write("Пропусков нет.\n")

    buf.write("\n")

    # Описательная статистика для числовых
    if numeric_cols:
        desc = df[numeric_cols].describe().round(2)
        buf.write("Описательная статистика (числовые):\n")
        buf.write(desc.to_string())
        buf.write("\n")

    return buf.getvalue()


def detect_anomalies(df: pd.DataFrame) -> tuple[str, list[io.BytesIO]]:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols:
        return "В данных нет числовых столбцов для поиска аномалий.", []

    report_lines = []
    charts = []
    anomaly_summary = {}

    for col in numeric_cols[:6]:  # макс 6 столбцов
        series = df[col].dropna()
        if len(series) < 4:
            continue

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        outliers = series[(series < lower) | (series > upper)]
        anomaly_summary[col] = {
            "total": len(series),
            "outliers": len(outliers),
            "pct": len(outliers) / len(series) * 100,
            "lower_bound": lower,
            "upper_bound": upper,
            "min": series.min(),
            "max": series.max(),
            "mean": series.mean(),
        }

        report_lines.append(
            f"• {col}: {len(outliers)} аномалий из {len(series)} "
            f"({len(outliers)/len(series)*100:.1f}%), "
            f"границы IQR: [{lower:.2f}, {upper:.2f}]"
        )

    # Строим боксплоты
    cols_to_plot = [c for c in numeric_cols[:6] if c in anomaly_summary]
    if cols_to_plot:
        fig, axes = plt.subplots(1, len(cols_to_plot), figsize=(4 * len(cols_to_plot), 5))
        if len(cols_to_plot) == 1:
            axes = [axes]
        for ax, col in zip(axes, cols_to_plot):
            data = df[col].dropna()
            bp = ax.boxplot(data, patch_artist=True)
            bp["boxes"][0].set_facecolor("#5B9BD5")
            ax.set_title(textwrap.fill(col, 15), fontsize=10)
            ax.tick_params(axis="x", labelbottom=False)
        fig.suptitle("Боксплоты — обнаружение аномалий (IQR)", fontsize=13, y=1.02)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        buf.seek(0)
        charts.append(buf)
        plt.close(fig)

    # Scatter с выделенными аномалиями (первые 2 числовых столбца)
    if len(cols_to_plot) >= 2:
        c1, c2 = cols_to_plot[0], cols_to_plot[1]
        subset = df[[c1, c2]].dropna()
        if len(subset) > 0:
            fig, ax = plt.subplots(figsize=(7, 5))

            s1 = subset[c1]
            q1_1, q3_1 = s1.quantile(0.25), s1.quantile(0.75)
            iqr1 = q3_1 - q1_1
            mask1 = (s1 < q1_1 - 1.5 * iqr1) | (s1 > q3_1 + 1.5 * iqr1)

            s2 = subset[c2]
            q1_2, q3_2 = s2.quantile(0.25), s2.quantile(0.75)
            iqr2 = q3_2 - q1_2
            mask2 = (s2 < q1_2 - 1.5 * iqr2) | (s2 > q3_2 + 1.5 * iqr2)

            outlier_mask = mask1 | mask2
            ax.scatter(
                subset.loc[~outlier_mask, c1], subset.loc[~outlier_mask, c2],
                alpha=0.4, s=15, label="Норма", color="#5B9BD5",
            )
            ax.scatter(
                subset.loc[outlier_mask, c1], subset.loc[outlier_mask, c2],
                alpha=0.8, s=30, label="Аномалии", color="#FF6B6B", marker="x",
            )
            ax.set_xlabel(c1)
            ax.set_ylabel(c2)
            ax.set_title(f"Аномалии: {c1} vs {c2}")
            ax.legend()
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
            buf.seek(0)
            charts.append(buf)
            plt.close(fig)

    report = "\n".join(report_lines) if report_lines else "Аномалий не обнаружено."
    return report, charts


def compute_correlations(df: pd.DataFrame) -> tuple[str, list[io.BytesIO]]:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if len(numeric_cols) < 2:
        return "Недостаточно числовых столбцов для корреляционного анализа.", []

    cols = numeric_cols[:10]  # макс 10
    corr = df[cols].corr().round(3)

    # Текстовый отчёт — топ пары
    pairs = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs.append((cols[i], cols[j], corr.iloc[i, j]))
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)

    report_lines = ["Топ корреляции:"]
    for c1, c2, r in pairs[:10]:
        report_lines.append(f"  • {c1} ↔ {c2}: {r:.3f}")

    # Heatmap
    charts = []
    fig, ax = plt.subplots(figsize=(max(6, len(cols)), max(5, len(cols) * 0.8)))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels([textwrap.fill(c, 12) for c in cols], rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels([textwrap.fill(c, 12) for c in cols], fontsize=8)

    for i in range(len(cols)):
        for j in range(len(cols)):
            val = corr.iloc[i, j]
            color = "white" if abs(val) > 0.5 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7, color=color)

    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Матрица корреляций", fontsize=13)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    buf.seek(0)
    charts.append(buf)
    plt.close(fig)

    return "\n".join(report_lines), charts


def analyze_trends(df: pd.DataFrame) -> tuple[str, list[io.BytesIO]]:
    charts = []
    report_lines = []

    # Ищем колонки с датами
    date_col = None
    for col in df.columns:
        if df[col].dtype == "object":
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().sum() > len(df) * 0.5:
                    date_col = col
                    df = df.copy()
                    df["_parsed_date"] = parsed
                    break
            except Exception:
                continue

    # Ищем колонки с годами
    year_col = None
    for col in df.columns:
        if "year" in col.lower():
            year_col = col
            break

    # Тренд по годам
    if year_col and pd.api.types.is_numeric_dtype(df[year_col]):
        year_counts = df[year_col].dropna().astype(int).value_counts().sort_index()
        if len(year_counts) > 1:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(year_counts.index, year_counts.values, marker="o", markersize=3, color="#5B9BD5")
            ax.fill_between(year_counts.index, year_counts.values, alpha=0.15, color="#5B9BD5")
            ax.set_xlabel("Год")
            ax.set_ylabel("Количество")
            ax.set_title(f"Тренд по {year_col}")
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
            buf.seek(0)
            charts.append(buf)
            plt.close(fig)
            report_lines.append(
                f"• {year_col}: от {year_counts.index.min()} до {year_counts.index.max()}, "
                f"пик — {year_counts.idxmax()} ({year_counts.max()} записей)"
            )

    # Тренд по дате добавления (по месяцам)
    if date_col:
        monthly = df.dropna(subset=["_parsed_date"]).set_index("_parsed_date").resample("ME").size()
        if len(monthly) > 1:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.bar(monthly.index, monthly.values, width=20, color="#5B9BD5", alpha=0.8)
            ax.set_xlabel("Дата")
            ax.set_ylabel("Количество")
            ax.set_title(f"Тренд по {date_col} (помесячно)")
            fig.autofmt_xdate()
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
            buf.seek(0)
            charts.append(buf)
            plt.close(fig)
            report_lines.append(f"• {date_col}: помесячный тренд построен")

    # Топ категорий
    cat_cols = df.select_dtypes(include="object").columns.tolist()
    cat_cols = [c for c in cat_cols if c != date_col and df[c].nunique() <= 30 and df[c].nunique() >= 2]

    for col in cat_cols[:3]:
        counts = df[col].value_counts().head(10)
        fig, ax = plt.subplots(figsize=(7, 4))
        bars = ax.barh(range(len(counts)), counts.values, color="#5B9BD5", alpha=0.8)
        ax.set_yticks(range(len(counts)))
        ax.set_yticklabels([textwrap.fill(str(v), 25) for v in counts.index], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Количество")
        ax.set_title(f"Топ-10: {col}")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        buf.seek(0)
        charts.append(buf)
        plt.close(fig)
        report_lines.append(f"• {col}: топ — «{counts.index[0]}» ({counts.values[0]})")

    report = "\n".join(report_lines) if report_lines else "Трендов и категорий не обнаружено."
    return report, charts
