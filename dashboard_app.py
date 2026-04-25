from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ModuleNotFoundError:
    px = None
    go = None
    PLOTLY_AVAILABLE = False


BASE_DATE_DEFAULT = pd.Timestamp("2025-12-31")
EXPECTED_FILES = {
    "center_order": "A1_final_center_order.csv",
    "center_stock": "A4_final_CENTER_STK.csv",
    "sales": "center_sales_final.csv",
    "preorder": "final_preorder.csv",
}
SEARCH_DIRS = [
    Path("."),
    Path("./data"),
    Path("./input"),
    Path("./inputs"),
]
SPEC_PATH = Path("/Users/elena/Downloads/대시보드용 데이터명세서.csv")
EXCLUDED_CENTER_CODES = {"20049", "20091"}
TOP_CATEGORY_NAME = "과자"
DATE_COLUMN_HINTS = {
    "center_order": ["ORD_YMD"],
    "center_stock": ["BIZ_DATE"],
    "sales": ["판매일자"],
    "preorder": ["NP_RLSE_YMD"],
}
NUMERIC_TEXT_COLUMNS = {
    "center_order": ["SUM(A.CONV_QTY)"],
}
KEY_COLUMNS = {
    "item_code": ["ITEM_CODE", "ITEM_CD"],
    "item_name": ["ITEM_NM", "ITEM_NAME", "상품명", "품목명"],
    "center_code": ["CENTER_CODE", "CENT_CD"],
    "center_name": ["CENTER_NM", "CENT_NM"],
    "category": ["ITEM_MDDV_NM", "중분류"],
    "subcategory": ["ITEM_SMDV_NM", "소분류"],
    "brand": ["BRAND", "브랜드"],
}


@dataclass
class DatasetInfo:
    key: str
    label: str
    path: Path | None
    frame: pd.DataFrame | None


METRIC_LABELS = {
    "preorder_qty": "예약주문량",
    "initial_order_qty": "초도발주량",
    "actual_sales_qty_7d": "매출 기반 실수요량(7일)",
}


def find_file(filename: str) -> Path | None:
    for directory in SEARCH_DIRS:
        candidate = (Path.cwd() / directory / filename).resolve()
        if candidate.exists():
            return candidate
    return None


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def infer_date_columns(frame: pd.DataFrame, dataset_key: str | None = None) -> list[str]:
    if dataset_key and dataset_key in DATE_COLUMN_HINTS:
        hinted = [column for column in DATE_COLUMN_HINTS[dataset_key] if column in frame.columns]
        if hinted:
            return hinted
    date_like = []
    for column in frame.columns:
        name = column.lower()
        if "date" in name or "dt" in name or "ymd" in name:
            date_like.append(column)
    return date_like


def infer_text_columns(frame: pd.DataFrame, keywords: Iterable[str]) -> list[str]:
    lowered = [keyword.lower() for keyword in keywords]
    matches = []
    for column in frame.columns:
        name = column.lower()
        if any(keyword in name for keyword in lowered):
            matches.append(column)
    return matches


def standardize_numeric_strings(frame: pd.DataFrame, dataset_key: str | None = None) -> pd.DataFrame:
    copied = frame.copy()
    target_columns = NUMERIC_TEXT_COLUMNS.get(dataset_key or "", [])
    for column in target_columns:
        if column in copied.columns:
            copied[column] = pd.to_numeric(copied[column].astype(str).str.replace(",", "", regex=False), errors="coerce")
    return copied


def prepare_dates(frame: pd.DataFrame, dataset_key: str | None = None) -> pd.DataFrame:
    copied = frame.copy()
    for column in infer_date_columns(copied, dataset_key):
        copied[column] = pd.to_datetime(copied[column], errors="coerce", format="%Y%m%d")
        if copied[column].isna().all():
            copied[column] = pd.to_datetime(frame[column], errors="coerce")
    return copied


def apply_filters(
    frame: pd.DataFrame,
    base_date: pd.Timestamp,
    filters: dict[str, list[str] | str],
    dataset_key: str | None = None,
) -> pd.DataFrame:
    filtered = standardize_numeric_strings(frame, dataset_key)
    filtered = prepare_dates(filtered, dataset_key)
    date_columns = infer_date_columns(filtered, dataset_key)
    if date_columns:
        earliest_date = filtered[date_columns].min(axis=1)
        filtered = filtered[earliest_date.isna() | (earliest_date <= base_date)]

    for column, selected in filters.items():
        if column not in filtered.columns:
            continue
        if isinstance(selected, str):
            if selected.strip():
                filtered = filtered[filtered[column].astype(str).str.contains(selected, case=False, na=False)]
        elif selected:
            filtered = filtered[filtered[column].astype(str).isin(selected)]
    return filtered


def pick_first_column(frame: pd.DataFrame, keywords: Iterable[str]) -> str | None:
    matches = infer_text_columns(frame, keywords)
    return matches[0] if matches else None


def find_matching_column(frame: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    for alias in aliases:
        if alias in frame.columns:
            return alias
    return None


def build_summary(frame: pd.DataFrame, dataset_key: str | None = None) -> dict[str, str]:
    summary = {
        "행 수": f"{len(frame):,}",
        "컬럼 수": f"{len(frame.columns):,}",
    }
    numeric_columns = frame.select_dtypes(include="number").columns.tolist()
    if numeric_columns:
        summary["수치형 컬럼"] = f"{len(numeric_columns):,}"
    date_columns = infer_date_columns(frame, dataset_key)
    if date_columns:
        values = prepare_dates(frame, dataset_key)[date_columns]
        min_date = values.min().min()
        max_date = values.max().max()
        if pd.notna(min_date) and pd.notna(max_date):
            summary["날짜 범위"] = f"{min_date.date()} ~ {max_date.date()}"
    return summary


@st.cache_data(show_spinner=False)
def load_specification() -> pd.DataFrame:
    if not SPEC_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(SPEC_PATH)


@st.cache_data(show_spinner=False)
def build_preorder_sales_analysis() -> pd.DataFrame:
    preorder_path = find_file(EXPECTED_FILES["preorder"])
    sales_path = find_file(EXPECTED_FILES["sales"])
    if not preorder_path or not sales_path:
        return pd.DataFrame()

    preorder = pd.read_csv(preorder_path, low_memory=False)
    sales = pd.read_csv(sales_path, low_memory=False)

    preorder["NP_RLSE_YMD"] = pd.to_datetime(preorder["NP_RLSE_YMD"].astype(str), format="%Y%m%d", errors="coerce")
    sales["판매일자"] = pd.to_datetime(sales["판매일자"], errors="coerce")
    sales["CENTER_SALE_QTY"] = pd.to_numeric(sales["CENTER_SALE_QTY"], errors="coerce").fillna(0)

    merged = preorder.merge(
        sales,
        left_on=["ITEM_CODE", "CENTER_NM"],
        right_on=["ITEM_CD", "CENT_NM"],
        how="left",
    )

    in_window = merged[
        (merged["판매일자"] >= merged["NP_RLSE_YMD"])
        & (merged["판매일자"] < merged["NP_RLSE_YMD"] + pd.Timedelta(days=7))
    ].copy()

    actual_sales = (
        in_window.groupby(["ITEM_CODE", "CENTER_NM"], as_index=False)["CENTER_SALE_QTY"]
        .sum()
        .rename(columns={"CENTER_SALE_QTY": "actual_sales_qty_7d"})
    )

    base = preorder.merge(actual_sales, on=["ITEM_CODE", "CENTER_NM"], how="left")
    base["actual_sales_qty_7d"] = base["actual_sales_qty_7d"].fillna(0)
    base["preorder_qty"] = pd.to_numeric(base["total_pre_order_qty(D-11~D-8)"], errors="coerce").fillna(0)
    base["initial_order_qty"] = pd.to_numeric(base["INITIAL_ORD_QTY"], errors="coerce").fillna(0)
    base["over_order_gap"] = base["initial_order_qty"] - base["actual_sales_qty_7d"]
    return base


def build_product_dashboard_table(analysis: pd.DataFrame) -> pd.DataFrame:
    if analysis.empty:
        return pd.DataFrame()

    grouped = (
        analysis.groupby(
            ["ITEM_MDDV_NM", "ITEM_SMDV_NM", "ITEM_CODE", "ITEM_NM"],
            as_index=False,
        )[["preorder_qty", "initial_order_qty", "actual_sales_qty_7d"]]
        .sum()
        .rename(
            columns={
                "ITEM_MDDV_NM": "중분류",
                "ITEM_SMDV_NM": "소분류",
                "ITEM_CODE": "제품코드",
                "ITEM_NM": "제품명",
                "preorder_qty": "예약주문 수",
                "initial_order_qty": "초도발주량",
                "actual_sales_qty_7d": "실수요",
            }
        )
        .sort_values(["중분류", "소분류", "제품명", "제품코드"])
    )
    grouped.insert(0, "대분류", TOP_CATEGORY_NAME)
    return grouped


def build_center_dashboard_table(analysis: pd.DataFrame) -> pd.DataFrame:
    if analysis.empty:
        return pd.DataFrame()

    grouped = (
        analysis.groupby(
            ["CENTER_CODE", "CENTER_NM", "ITEM_MDDV_NM", "ITEM_SMDV_NM", "ITEM_CODE", "ITEM_NM"],
            as_index=False,
        )[["preorder_qty", "initial_order_qty", "actual_sales_qty_7d"]]
        .sum()
        .rename(
            columns={
                "CENTER_CODE": "센터코드",
                "CENTER_NM": "센터",
                "ITEM_MDDV_NM": "중분류",
                "ITEM_SMDV_NM": "소분류",
                "ITEM_CODE": "제품코드",
                "ITEM_NM": "제품명",
                "preorder_qty": "예약주문 수",
                "initial_order_qty": "초도발주량",
                "actual_sales_qty_7d": "실수요",
            }
        )
        .sort_values(["센터코드", "센터", "중분류", "소분류", "제품명", "제품코드"])
    )
    grouped.insert(2, "대분류", TOP_CATEGORY_NAME)
    return grouped


@st.cache_data(show_spinner=False)
def load_center_selector_options() -> pd.DataFrame:
    order_path = find_file(EXPECTED_FILES["center_order"])
    preorder_path = find_file(EXPECTED_FILES["preorder"])
    if not order_path or not preorder_path:
        return pd.DataFrame()

    order = pd.read_csv(order_path, usecols=["CENT_CD"], low_memory=False)
    preorder = pd.read_csv(preorder_path, usecols=["CENTER_CODE", "CENTER_NM"], low_memory=False)

    order["CENT_CD"] = order["CENT_CD"].astype(str)
    preorder["CENTER_CODE"] = preorder["CENTER_CODE"].astype(str)
    order = order[~order["CENT_CD"].isin(EXCLUDED_CENTER_CODES)].copy()
    preorder = preorder[~preorder["CENTER_CODE"].isin(EXCLUDED_CENTER_CODES)].copy()

    center_codes = (
        order["CENT_CD"]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .sort_values()
        .to_frame(name="센터코드")
    )
    center_names = (
        preorder[["CENTER_CODE", "CENTER_NM"]]
        .dropna()
        .drop_duplicates()
        .rename(columns={"CENTER_CODE": "센터코드", "CENTER_NM": "센터"})
    )

    options = center_codes.merge(center_names, on="센터코드", how="left")
    options["센터"] = options["센터"].fillna("이름없음")
    options["label"] = options["센터코드"] + " | " + options["센터"]
    return options


@st.cache_data(show_spinner=False)
def build_reference_item_analysis() -> pd.DataFrame:
    analysis = build_preorder_sales_analysis()
    if analysis.empty:
        return pd.DataFrame()

    item_df = (
        analysis.groupby("ITEM_CODE", as_index=False)
        .agg(
            ITEM_NM=("ITEM_NM", "first"),
            NP_RLSE_YMD=("NP_RLSE_YMD", "first"),
            BRAND=("BRAND", "first"),
            ITEM_MDDV_NM=("ITEM_MDDV_NM", "first"),
            ITEM_SMDV_NM=("ITEM_SMDV_NM", "first"),
            GOAL_INTRO_RT=("GOAL_INTRO_RT", "first"),
            MIN_ORD_QTY=("MIN_ORD_QTY", "first"),
            ST_CPM_AMT=("ST_CPM_AMT", "first"),
            ST_SLEM_AMT=("ST_SLEM_AMT", "first"),
            초도발주량=("initial_order_qty", "sum"),
            초기예약발주=("preorder_qty", "sum"),
            실수요량=("actual_sales_qty_7d", "sum"),
            참여점포수=("ordering_store_cnt", "sum"),
            전체점포수=("total_store_cnt", "sum"),
        )
    )

    datasets = load_datasets()
    center_order = next((item.frame for item in datasets if item.key == "center_order"), None)
    if center_order is not None and "ITEM_CD" in center_order.columns and "SUM(A.CONV_QTY)" in center_order.columns:
        shipped = (
            center_order.groupby("ITEM_CD", as_index=False)["SUM(A.CONV_QTY)"]
            .sum()
            .rename(columns={"ITEM_CD": "ITEM_CODE", "SUM(A.CONV_QTY)": "실출고량"})
        )
        item_df = item_df.merge(shipped, on="ITEM_CODE", how="left")
    item_df["실출고량"] = item_df.get("실출고량", 0).fillna(0)

    safe_initial = item_df["초도발주량"].replace(0, pd.NA)
    safe_ship = item_df["실출고량"].replace(0, pd.NA)
    item_df["실제출고율(%)"] = (item_df["실출고량"] / safe_initial * 100).round(1)
    item_df["결품여부"] = item_df["실수요량"] > item_df["실출고량"]
    item_df["부진여부"] = (item_df["실출고량"] > 0) & ((item_df["실수요량"] / safe_ship) < 0.5)
    item_df["출시일자"] = pd.to_datetime(item_df["NP_RLSE_YMD"], errors="coerce")
    item_df["상태"] = item_df.apply(lambda row: "결품" if row["결품여부"] else ("부진" if row["부진여부"] else "정상"), axis=1)
    return item_df


@st.cache_data(show_spinner=False)
def load_datasets() -> list[DatasetInfo]:
    labels = {
        "center_order": "센터 발주 Raw",
        "center_stock": "센터 재고 Raw",
        "sales": "매출/수요 Raw",
        "preorder": "예약주문 Raw",
    }
    datasets: list[DatasetInfo] = []
    for key, filename in EXPECTED_FILES.items():
        path = find_file(filename)
        frame = standardize_numeric_strings(load_csv(path), key) if path else None
        datasets.append(DatasetInfo(key=key, label=labels[key], path=path, frame=frame))
    return datasets


def render_dataset_card(dataset: DatasetInfo) -> None:
    st.subheader(dataset.label)
    if not dataset.path or dataset.frame is None:
        st.warning(f"`{EXPECTED_FILES[dataset.key]}` 파일을 찾지 못했습니다.")
        return

    st.caption(str(dataset.path))
    summary = build_summary(dataset.frame, dataset.key)
    metrics = st.columns(len(summary))
    for column, (label, value) in zip(metrics, summary.items()):
        column.metric(label, value)


def render_raw_view(dataset: DatasetInfo, base_date: pd.Timestamp) -> None:
    if dataset.frame is None:
        return

    frame = dataset.frame
    category_col = find_matching_column(frame, KEY_COLUMNS["category"])
    subcategory_col = find_matching_column(frame, KEY_COLUMNS["subcategory"])
    brand_col = find_matching_column(frame, KEY_COLUMNS["brand"])
    item_name_col = find_matching_column(frame, KEY_COLUMNS["item_name"])
    center_name_col = find_matching_column(frame, KEY_COLUMNS["center_name"])

    with st.expander(f"{dataset.label} 필터", expanded=False):
        filters: dict[str, list[str] | str] = {}
        columns = st.columns(5)
        widget_prefix = f"raw_view_{dataset.key}"

        if category_col:
            options = sorted(frame[category_col].dropna().astype(str).unique().tolist())
            filters[category_col] = columns[0].multiselect(
                "중분류",
                options,
                key=f"{widget_prefix}_{category_col}_multiselect",
            )
        if subcategory_col:
            options = sorted(frame[subcategory_col].dropna().astype(str).unique().tolist())
            filters[subcategory_col] = columns[1].multiselect(
                "소분류",
                options,
                key=f"{widget_prefix}_{subcategory_col}_multiselect",
            )
        if brand_col:
            options = sorted(frame[brand_col].dropna().astype(str).unique().tolist())
            filters[brand_col] = columns[2].multiselect(
                "브랜드",
                options,
                key=f"{widget_prefix}_{brand_col}_multiselect",
            )
        if item_name_col:
            filters[item_name_col] = columns[3].text_input(
                "상품명 검색",
                key=f"{widget_prefix}_item_name_search_{item_name_col}",
            )
        if center_name_col:
            options = sorted(frame[center_name_col].dropna().astype(str).unique().tolist())
            filters[center_name_col] = columns[4].multiselect(
                "센터",
                options,
                key=f"{widget_prefix}_{center_name_col}_multiselect",
            )

        filtered = apply_filters(frame, base_date, filters, dataset.key)

    left, right = st.columns([2, 1])
    left.dataframe(filtered, use_container_width=True, height=420)
    csv = filtered.to_csv(index=False).encode("utf-8-sig")
    right.download_button(
        label=f"{dataset.key}_filtered.csv 다운로드",
        data=csv,
        file_name=f"{dataset.key}_filtered.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"raw_view_{dataset.key}_download_button",
    )
    right.write(f"조회 건수: {len(filtered):,}")
    date_columns = infer_date_columns(filtered, dataset.key)
    if date_columns:
        right.write("날짜 컬럼")
        right.write(", ".join(date_columns))


def render_full_raw_view(dataset: DatasetInfo) -> None:
    if dataset.frame is None:
        return

    st.subheader(f"{dataset.label} 전체 Raw")
    st.caption("원본 전체 행을 기준일 필터 없이 그대로 보여줍니다.")

    frame = dataset.frame
    csv = frame.to_csv(index=False).encode("utf-8-sig")

    top_left, top_right = st.columns([3, 1])
    top_left.dataframe(frame, use_container_width=True, height=420)
    top_right.download_button(
        label=f"{dataset.key}_full_raw.csv 다운로드",
        data=csv,
        file_name=f"{dataset.key}_full_raw.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"full_raw_{dataset.key}_download_button",
    )
    top_right.write(f"전체 건수: {len(frame):,}")
    top_right.write(f"전체 컬럼 수: {len(frame.columns):,}")


def render_raw_workspace(connected: list[DatasetInfo]) -> None:
    st.subheader("Raw Data Viewer")
    st.caption("파일을 하나 선택해서 컬럼 설명과 전체 raw 데이터를 단순하게 확인합니다.")

    dataset_labels = {dataset.label: dataset for dataset in connected}
    selected_label = st.selectbox(
        "데이터셋 선택",
        list(dataset_labels.keys()),
        key="raw_workspace_dataset_selectbox",
    )
    dataset = dataset_labels[selected_label]
    frame = dataset.frame
    if frame is None:
        st.info("선택한 파일을 불러오지 못했습니다.")
        return

    spec = load_specification()
    dataset_filename = EXPECTED_FILES[dataset.key]
    dataset_spec = spec[spec["소스파일"] == dataset_filename].copy() if not spec.empty else pd.DataFrame()
    available_columns = frame.columns.tolist()

    selected_columns = st.multiselect(
        "표시할 컬럼",
        available_columns,
        default=available_columns,
        key=f"raw_workspace_columns_{dataset.key}",
    )
    keyword = st.text_input(
        "검색",
        placeholder="상품명, 상품코드, 센터명 등으로 검색",
        key=f"raw_workspace_search_{dataset.key}",
    )

    filtered = frame.copy()
    if keyword.strip():
        mask = filtered.astype(str).apply(
            lambda column: column.str.contains(keyword, case=False, na=False)
        )
        filtered = filtered[mask.any(axis=1)]

    view_columns = selected_columns or available_columns

    summary_cols = st.columns(4)
    summary_cols[0].metric("파일", dataset_filename)
    summary_cols[1].metric("전체 행 수", f"{len(frame):,}")
    summary_cols[2].metric("검색 후 행 수", f"{len(filtered):,}")
    summary_cols[3].metric("표시 컬럼 수", f"{len(view_columns):,}")

    left, right = st.columns([2.2, 1])
    left.write("전체 Raw Table")
    left.dataframe(filtered[view_columns], use_container_width=True, height=520)

    csv = filtered[view_columns].to_csv(index=False).encode("utf-8-sig")
    right.download_button(
        label=f"{dataset.key}_workspace_view.csv 다운로드",
        data=csv,
        file_name=f"{dataset.key}_workspace_view.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"raw_workspace_download_{dataset.key}",
    )

    right.write("컬럼 목록")
    right.dataframe(
        pd.DataFrame({"컬럼명": view_columns}),
        use_container_width=True,
        height=240,
    )

    right.write("데이터 명세")
    if dataset_spec.empty:
        right.info("연결된 컬럼 명세가 없습니다.")
    else:
        spec_display = dataset_spec[dataset_spec["컬럼명"].isin(view_columns)][["컬럼명", "Type", "Comment"]]
        right.dataframe(spec_display, use_container_width=True, height=240)


def render_product_dashboard(base_date: pd.Timestamp) -> None:
    analysis = build_preorder_sales_analysis()
    if analysis.empty:
        st.info("`final_preorder.csv`와 `center_sales_final.csv`가 있어야 제품 대시보드를 만들 수 있습니다.")
        return

    analysis = analysis[analysis["NP_RLSE_YMD"].le(base_date)].copy()
    analysis = analysis[~analysis["CENTER_CODE"].astype(str).isin(EXCLUDED_CENTER_CODES)].copy()
    if analysis.empty:
        st.info("기준일 이전 데이터가 없습니다.")
        return

    filters = st.columns([1, 1, 1, 1, 1.4, 1])
    view_mode = filters[0].selectbox(
        "보기 기준",
        ["제품별", "센터별"],
        key="product_dashboard_view_mode",
    )
    selected_top_category = filters[1].selectbox(
        "대분류",
        [TOP_CATEGORY_NAME],
        key="product_dashboard_top_category",
    )

    center_options = load_center_selector_options()
    if center_options.empty:
        selected_center_label = filters[2].selectbox("센터", ["전체"], key="product_dashboard_center_fallback")
        selected_center_code = "전체"
    else:
        center_labels = ["전체"] + center_options["label"].tolist()
        selected_center_label = filters[2].selectbox("센터", center_labels, key="product_dashboard_center")
        selected_center_code = "전체"
        if selected_center_label != "전체":
            selected_center_code = center_options.loc[
                center_options["label"] == selected_center_label,
                "센터코드",
            ].iloc[0]
            analysis = analysis[analysis["CENTER_CODE"].astype(str) == str(selected_center_code)].copy()

    product_table = build_product_dashboard_table(analysis)
    center_table = build_center_dashboard_table(analysis)
    dashboard_table = center_table.copy() if view_mode == "센터별" else product_table.copy()
    if dashboard_table.empty:
        st.info("선택한 조건에 맞는 데이터가 없습니다.")
        return

    if selected_top_category != "전체":
        dashboard_table = dashboard_table[dashboard_table["대분류"].astype(str) == selected_top_category]
    if dashboard_table.empty:
        st.info("선택한 대분류에 맞는 데이터가 없습니다.")
        return

    mddv_options = ["전체"] + sorted(dashboard_table["중분류"].dropna().astype(str).unique().tolist())
    selected_mddv = filters[3].selectbox("중분류", mddv_options, key="product_dashboard_mddv")

    filtered = dashboard_table.copy()
    if selected_mddv != "전체":
        filtered = filtered[filtered["중분류"].astype(str) == selected_mddv]

    smdv_options = ["전체"] + sorted(filtered["소분류"].dropna().astype(str).unique().tolist())
    selected_smdv = filters[4].selectbox("소분류", smdv_options, key="product_dashboard_smdv")
    if selected_smdv != "전체":
        filtered = filtered[filtered["소분류"].astype(str) == selected_smdv]

    keyword = filters[5].text_input("제품 검색", placeholder="제품코드 또는 제품명", key="product_dashboard_keyword")
    if keyword.strip():
        filtered = filtered[
            filtered["제품코드"].astype(str).str.contains(keyword, case=False, na=False)
            | filtered["제품명"].astype(str).str.contains(keyword, case=False, na=False)
        ]

    sort_choice = st.selectbox(
        "정렬 기준",
        ["예약주문 수", "초도발주량", "실수요"],
        key="product_dashboard_sort",
    )
    filtered = filtered.sort_values(sort_choice, ascending=False)

    summary_cols = st.columns(4)
    summary_cols[0].metric("제품 수", f"{len(filtered):,}")
    summary_cols[1].metric("예약주문 합계", f"{filtered['예약주문 수'].sum():,.0f}")
    summary_cols[2].metric("초도발주 합계", f"{filtered['초도발주량'].sum():,.0f}")
    summary_cols[3].metric("실수요 합계", f"{filtered['실수요'].sum():,.0f}")

    display_columns = ["대분류", "중분류", "소분류", "제품코드", "제품명", "예약주문 수", "초도발주량", "실수요"]
    if view_mode == "센터별":
        display_columns = ["센터코드", "센터"] + display_columns
    st.dataframe(
        filtered[display_columns],
        use_container_width=True,
        height=560,
    )

    csv = filtered[display_columns].to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "통합 테이블 다운로드",
        data=csv,
        file_name="product_dashboard_table.csv",
        mime="text/csv",
        use_container_width=True,
        key="product_dashboard_download",
    )


def render_cross_dataset_overview(available: list[DatasetInfo], base_date: pd.Timestamp) -> None:
    st.subheader("기준일 이전 데이터 현황")
    overview_rows = []
    for dataset in available:
        if dataset.frame is None:
            continue
        filtered = apply_filters(dataset.frame, base_date, {}, dataset.key)
        row = {
            "dataset": dataset.label,
            "rows_before_base_date": len(filtered),
            "columns": len(filtered.columns),
            "date_columns": ", ".join(infer_date_columns(filtered, dataset.key)) or "-",
        }
        overview_rows.append(row)

    if overview_rows:
        st.dataframe(pd.DataFrame(overview_rows), use_container_width=True, height=220)
    else:
        st.info("현재 연결된 CSV가 없어 개요를 만들 수 없습니다.")


def render_past_product_lookup(available: list[DatasetInfo], base_date: pd.Timestamp) -> None:
    st.subheader("과거 신상품/유사 사례 조회")
    preorder_dataset = next((item for item in available if item.key == "preorder" and item.frame is not None), None)
    order_dataset = next((item for item in available if item.key == "center_order" and item.frame is not None), None)

    target = preorder_dataset or order_dataset
    if target is None or target.frame is None:
        st.info("예약주문 또는 센터 발주 파일이 있어야 과거 사례 조회를 구성할 수 있습니다.")
        return

    frame = apply_filters(target.frame, base_date, {}, target.key)
    item_col = find_matching_column(frame, KEY_COLUMNS["item_name"])
    item_code_col = find_matching_column(frame, KEY_COLUMNS["item_code"])
    center_name_col = find_matching_column(frame, KEY_COLUMNS["center_name"])
    category_col = find_matching_column(frame, KEY_COLUMNS["category"])
    subcategory_col = find_matching_column(frame, KEY_COLUMNS["subcategory"])

    query = st.text_input(
        "상품명 또는 키워드",
        placeholder="예: 초코, 감자, 젤리",
        key=f"past_product_lookup_{target.key}_query",
    )
    filtered = frame.copy()
    if item_col and query.strip():
        filtered = filtered[filtered[item_col].astype(str).str.contains(query, case=False, na=False)]

    show_columns = [column for column in [item_code_col, item_col, center_name_col, category_col, subcategory_col] if column]
    preferred_columns = [
        "NP_RLSE_YMD",
        "INITIAL_ORD_QTY",
        "total_pre_order_qty(D-11~D-8)",
        "SUM(A.CONV_QTY)",
        "CENTER_SALE_QTY",
    ]
    show_columns += [column for column in preferred_columns if column in filtered.columns and column not in show_columns]
    show_columns += [column for column in filtered.columns if column not in show_columns][:5]
    st.dataframe(filtered[show_columns], use_container_width=True, height=320)


def render_current_release_focus(available: list[DatasetInfo], base_date: pd.Timestamp) -> None:
    st.subheader("기준일 시점 신상품 관점")
    preorder_dataset = next((item for item in available if item.key == "preorder" and item.frame is not None), None)
    if preorder_dataset is None or preorder_dataset.frame is None:
        st.info("`final_preorder.csv`가 있어야 현재 시점 기준 신상품 목록을 볼 수 있습니다.")
        return

    frame = prepare_dates(preorder_dataset.frame, preorder_dataset.key)
    if "NP_RLSE_YMD" not in frame.columns:
        st.info("출시일 컬럼을 찾지 못했습니다.")
        return

    release_window = frame[
        frame["NP_RLSE_YMD"].between(base_date - pd.Timedelta(days=31), base_date, inclusive="both")
    ].copy()
    release_window = release_window.sort_values("NP_RLSE_YMD", ascending=False)

    summary_cols = st.columns(4)
    summary_cols[0].metric("기준월 신상품 행 수", f"{len(release_window):,}")
    if "ITEM_CODE" in release_window.columns:
        summary_cols[1].metric("기준월 상품 수", f"{release_window['ITEM_CODE'].nunique():,}")
    if "CENTER_CODE" in release_window.columns:
        summary_cols[2].metric("센터 수", f"{release_window['CENTER_CODE'].nunique():,}")
    if "INITIAL_ORD_QTY" in release_window.columns:
        summary_cols[3].metric("초도발주 합계", f"{release_window['INITIAL_ORD_QTY'].fillna(0).sum():,.0f}")

    show_columns = [
        column
        for column in [
            "NP_RLSE_YMD",
            "ITEM_CODE",
            "ITEM_NM",
            "CENTER_NM",
            "BRAND",
            "ITEM_MDDV_NM",
            "ITEM_SMDV_NM",
            "total_pre_order_qty(D-11~D-8)",
            "INITIAL_ORD_QTY",
        ]
        if column in release_window.columns
    ]
    st.dataframe(release_window[show_columns], use_container_width=True, height=320)


def render_category_drilldown(base_date: pd.Timestamp) -> None:
    st.subheader("중/소분류별 예약주문 · 초도발주 · 실수요 비교")
    st.caption("실수요량은 출시일 이후 7일간의 센터 매출 수량 합계 기준입니다.")

    analysis = build_preorder_sales_analysis()
    if analysis.empty:
        st.info("`final_preorder.csv`와 `center_sales_final.csv`가 있어야 카테고리 드릴다운을 만들 수 있습니다.")
        return

    analysis = analysis[analysis["NP_RLSE_YMD"].le(base_date)].copy()
    if analysis.empty:
        st.info("기준일 이전 데이터가 없습니다.")
        return

    mddv_options = sorted(analysis["ITEM_MDDV_NM"].dropna().astype(str).unique().tolist())
    selected_mddv = st.selectbox(
        "중분류",
        mddv_options,
        index=0,
        key="category_drilldown_mddv_selectbox",
    )

    scoped = analysis[analysis["ITEM_MDDV_NM"].astype(str) == selected_mddv].copy()
    smdv_options = sorted(scoped["ITEM_SMDV_NM"].dropna().astype(str).unique().tolist())
    selected_smdv = st.selectbox(
        "소분류",
        smdv_options,
        index=0 if smdv_options else None,
        key=f"category_drilldown_{selected_mddv}_smdv_selectbox",
    )

    if selected_smdv:
        scoped = scoped[scoped["ITEM_SMDV_NM"].astype(str) == selected_smdv].copy()

    item_options = (
        scoped[["ITEM_CODE", "ITEM_NM"]]
        .drop_duplicates()
        .sort_values(["ITEM_NM", "ITEM_CODE"])
        .assign(label=lambda df: df["ITEM_NM"].astype(str) + " (" + df["ITEM_CODE"].astype(str) + ")")
    )
    selected_item_label = st.selectbox(
        "상품",
        item_options["label"].tolist(),
        key=f"category_drilldown_{selected_mddv}_{selected_smdv}_item_selectbox",
    )
    selected_item_code = int(item_options.loc[item_options["label"] == selected_item_label, "ITEM_CODE"].iloc[0])

    category_summary = scoped.groupby(["ITEM_MDDV_NM", "ITEM_SMDV_NM"], as_index=False)[
        ["preorder_qty", "initial_order_qty", "actual_sales_qty_7d"]
    ].sum()

    item_scoped = scoped[scoped["ITEM_CODE"] == selected_item_code].copy()
    item_summary = item_scoped.groupby(["ITEM_CODE", "ITEM_NM"], as_index=False)[
        ["preorder_qty", "initial_order_qty", "actual_sales_qty_7d", "over_order_gap"]
    ].sum()
    item_center_view = item_scoped[
        [
            "CENTER_NM",
            "NP_RLSE_YMD",
            "preorder_qty",
            "initial_order_qty",
            "actual_sales_qty_7d",
            "over_order_gap",
        ]
    ].sort_values(["initial_order_qty", "actual_sales_qty_7d"], ascending=False)

    metrics = item_summary.iloc[0]
    top_cols = st.columns(4)
    top_cols[0].metric("예약주문량", f"{metrics['preorder_qty']:,.0f}")
    top_cols[1].metric("초도발주량", f"{metrics['initial_order_qty']:,.0f}")
    top_cols[2].metric("매출 기반 실수요량", f"{metrics['actual_sales_qty_7d']:,.0f}")
    top_cols[3].metric("과발주 갭", f"{metrics['over_order_gap']:,.0f}")

    chart_source = pd.DataFrame(
        {
            "지표": [METRIC_LABELS["preorder_qty"], METRIC_LABELS["initial_order_qty"], METRIC_LABELS["actual_sales_qty_7d"]],
            "수량": [metrics["preorder_qty"], metrics["initial_order_qty"], metrics["actual_sales_qty_7d"]],
        }
    )

    left, right = st.columns([1.2, 1])
    left.write("선택 상품 요약")
    left.bar_chart(chart_source.set_index("지표"))

    right.write("선택 소분류 합계")
    category_display = category_summary.rename(
        columns={
            "ITEM_MDDV_NM": "중분류",
            "ITEM_SMDV_NM": "소분류",
            "preorder_qty": "예약주문량",
            "initial_order_qty": "초도발주량",
            "actual_sales_qty_7d": "매출 기반 실수요량(7일)",
        }
    )
    right.dataframe(category_display, use_container_width=True, height=220)

    st.write("센터별 상세")
    detail_display = item_center_view.rename(
        columns={
            "CENTER_NM": "센터",
            "NP_RLSE_YMD": "출시일",
            "preorder_qty": "예약주문량",
            "initial_order_qty": "초도발주량",
            "actual_sales_qty_7d": "매출 기반 실수요량(7일)",
            "over_order_gap": "과발주 갭",
        }
    )
    st.dataframe(detail_display, use_container_width=True, height=360)


def render_reference_app_tab(base_date: pd.Timestamp) -> None:
    item_df = build_reference_item_analysis()
    datasets = load_datasets()
    preorder_dataset = next((item for item in datasets if item.key == "preorder"), None)
    center_order_dataset = next((item for item in datasets if item.key == "center_order"), None)
    sales_dataset = next((item for item in datasets if item.key == "sales"), None)
    if item_df.empty or preorder_dataset is None or preorder_dataset.frame is None:
        st.info("참고 탭을 만들 데이터가 부족합니다.")
        return

    item_df = item_df[item_df["출시일자"].le(base_date)].copy()
    preorder = preorder_dataset.frame.copy()
    orders_raw = center_order_dataset.frame.copy() if center_order_dataset and center_order_dataset.frame is not None else pd.DataFrame()
    sales = sales_dataset.frame.copy() if sales_dataset and sales_dataset.frame is not None else pd.DataFrame()

    fc1, fc2, fc3 = st.columns([2, 2, 3])
    all_mddv = sorted(item_df["ITEM_MDDV_NM"].dropna().astype(str).unique().tolist())
    sel_mddv = fc1.multiselect("중분류", all_mddv, key="ref_tab_mddv")
    smdv_pool = item_df[item_df["ITEM_MDDV_NM"].isin(sel_mddv)] if sel_mddv else item_df
    sel_smdv = fc2.multiselect(
        "소분류",
        sorted(smdv_pool["ITEM_SMDV_NM"].dropna().astype(str).unique().tolist()),
        key="ref_tab_smdv",
    )
    search_nm = fc3.text_input("상품명 검색", key="ref_tab_search")

    filtered = item_df.copy()
    if sel_mddv:
        filtered = filtered[filtered["ITEM_MDDV_NM"].isin(sel_mddv)]
    if sel_smdv:
        filtered = filtered[filtered["ITEM_SMDV_NM"].isin(sel_smdv)]
    if search_nm:
        filtered = filtered[filtered["ITEM_NM"].astype(str).str.contains(search_nm, na=False)]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("조회 상품 수", f"{len(filtered):,}")
    k2.metric("총 초도발주량", f"{filtered['초도발주량'].sum():,.0f}")
    k3.metric("총 실출고량", f"{filtered['실출고량'].sum():,.0f}")
    k4.metric("총 실수요량", f"{filtered['실수요량'].sum():,.0f}")

    tbl = filtered[[
        "ITEM_CODE", "ITEM_NM", "출시일자", "BRAND", "ITEM_MDDV_NM", "ITEM_SMDV_NM",
        "초도발주량", "초기예약발주", "실출고량", "실수요량", "실제출고율(%)"
    ]].rename(columns={
        "ITEM_CODE": "상품코드",
        "ITEM_NM": "상품명",
        "BRAND": "브랜드",
        "ITEM_MDDV_NM": "중분류",
        "ITEM_SMDV_NM": "소분류",
    }).copy()
    tbl["출시일자"] = tbl["출시일자"].dt.strftime("%Y-%m-%d")
    st.dataframe(tbl.set_index("상품코드"), use_container_width=True, height=320)

    item_opts = filtered[["ITEM_CODE", "ITEM_NM"]].drop_duplicates().reset_index(drop=True)
    if item_opts.empty:
        st.info("필터 조건에 해당하는 상품이 없습니다.")
        return

    labels = (item_opts["ITEM_NM"] + " [" + item_opts["ITEM_CODE"].astype(str) + "]").tolist()
    sel_idx = st.selectbox("상품 선택", options=range(len(labels)), format_func=lambda i: labels[i], key="ref_tab_item")
    sel_code = int(item_opts.loc[sel_idx, "ITEM_CODE"])

    col_l, col_r = st.columns(2, gap="large")
    item_pre = preorder[preorder["ITEM_CODE"] == sel_code].copy()

    with col_l:
        st.markdown("##### 신상품 정보")
        if not item_pre.empty:
            b = item_pre.iloc[0]
            launch_dt = pd.to_datetime(str(int(b["NP_RLSE_YMD"])), format="%Y%m%d", errors="coerce")
            info_rows = [
                ("상품코드", str(b["ITEM_CODE"])),
                ("상품명", b["ITEM_NM"]),
                ("출시일자", launch_dt.strftime("%Y-%m-%d") if pd.notna(launch_dt) else "-"),
                ("브랜드", b["BRAND"]),
                ("중분류", b["ITEM_MDDV_NM"]),
                ("소분류", b["ITEM_SMDV_NM"]),
                ("목표도입율", f"{b['GOAL_INTRO_RT']:.0f}%"),
                ("최소발주수량", f"{b['MIN_ORD_QTY']:.0f}"),
                ("총 초도발주량", f"{item_pre['INITIAL_ORD_QTY'].sum():,.0f}"),
                ("총 사전예약발주", f"{item_pre['total_pre_order_qty(D-11~D-8)'].sum():,.0f}"),
            ]
            st.dataframe(pd.DataFrame(info_rows, columns=["항목", "내용"]).set_index("항목"), use_container_width=True, height=300)

            d_cols = ["D-11", "D-10", "D-9", "D-8", "D-7", "D-6", "D-5", "D-4", "D-3", "D-2", "D-1", "D-0"]
            d_df = pd.DataFrame(
                [{"D-day": dc, "발주수량": float(pd.to_numeric(item_pre[dc], errors="coerce").sum())} for dc in d_cols if dc in item_pre.columns]
            )
            if not d_df.empty and d_df["발주수량"].sum() > 0:
                if PLOTLY_AVAILABLE:
                    fig_d = px.bar(d_df, x="D-day", y="발주수량", color_discrete_sequence=["#1D4ED8"], height=220)
                    fig_d.update_layout(margin=dict(l=0, r=0, t=10, b=0), plot_bgcolor="white", paper_bgcolor="white", showlegend=False)
                    st.plotly_chart(fig_d, use_container_width=True)
                else:
                    st.bar_chart(d_df.set_index("D-day"), use_container_width=True)

    with col_r:
        st.markdown("##### 센터별 예약주문 · 초도발주량 · 실수요량")
        if not item_pre.empty:
            center_pre = item_pre[["CENTER_CODE", "CENTER_NM", "INITIAL_ORD_QTY", "total_pre_order_qty(D-11~D-8)", "ordering_store_cnt", "total_store_cnt"]].copy()
            center_pre.columns = ["센터코드", "센터명", "초도발주량", "사전예약발주", "참여점포", "전체점포"]
            center_pre["센터코드"] = pd.to_numeric(center_pre["센터코드"], errors="coerce")

            c_orders = pd.DataFrame(columns=["센터코드", "실출고량"])
            if not orders_raw.empty:
                c_orders = (
                    orders_raw[orders_raw["ITEM_CD"] == sel_code]
                    .groupby("CENT_CD", as_index=False)["SUM(A.CONV_QTY)"]
                    .sum()
                )
                c_orders.columns = ["센터코드", "실출고량"]
                c_orders["센터코드"] = pd.to_numeric(c_orders["센터코드"], errors="coerce")

            c_sales = pd.DataFrame(columns=["센터명", "실수요량"])
            if not sales.empty:
                c_sales = sales[sales["ITEM_CD"] == sel_code].groupby("CENT_NM", as_index=False)["CENTER_SALE_QTY"].sum()
                c_sales.columns = ["센터명", "실수요량"]

            c_merged = center_pre.merge(c_orders, on="센터코드", how="left").merge(c_sales, on="센터명", how="left")
            c_merged["실출고량"] = c_merged["실출고량"].fillna(0)
            c_merged["실수요량"] = c_merged["실수요량"].fillna(0)
            safe_init = c_merged["초도발주량"].replace(0, pd.NA)
            c_merged["출고율(%)"] = (c_merged["실출고량"] / safe_init * 100).round(1)

            st.dataframe(
                c_merged.set_index("센터명")[["사전예약발주", "초도발주량", "실수요량", "참여점포", "전체점포"]],
                use_container_width=True,
                height=300,
            )

            if PLOTLY_AVAILABLE:
                fig_c = go.Figure()
                fig_c.add_trace(go.Bar(name="예약주문", x=c_merged["센터명"], y=c_merged["사전예약발주"], marker_color="#93C5FD"))
                fig_c.add_trace(go.Bar(name="초도발주량", x=c_merged["센터명"], y=c_merged["초도발주량"], marker_color="#1D4ED8"))
                fig_c.add_trace(go.Bar(name="실수요량", x=c_merged["센터명"], y=c_merged["실수요량"], marker_color="#1E3A8A"))
                fig_c.update_layout(barmode="group", height=290, margin=dict(l=0, r=0, t=20, b=80), plot_bgcolor="white", paper_bgcolor="white")
                st.plotly_chart(fig_c, use_container_width=True)
            else:
                fallback_chart = c_merged.set_index("센터명")[["사전예약발주", "초도발주량", "실수요량"]]
                st.bar_chart(fallback_chart, use_container_width=True)


def main() -> None:
    st.set_page_config(
        page_title="신상품 과거 Raw Data",
        page_icon="📊",
        layout="wide",
    )
    st.title("신상품 과거 Raw Data")

    datasets = load_datasets()

    with st.sidebar:
        st.header("조회 기준")
        base_date = pd.Timestamp(st.date_input("기준일", BASE_DATE_DEFAULT.date(), key="sidebar_base_date_input"))
        st.caption("기준일 이후 데이터는 자동으로 제외합니다.")
        st.divider()
        st.write("파일 연결 상태")
        for dataset in datasets:
            if dataset.path:
                st.success(f"{dataset.label}: 연결됨")
            else:
                st.warning(f"{dataset.label}: 없음")

    connected = [dataset for dataset in datasets if dataset.frame is not None]

    if not connected:
        st.error("현재 작업폴더에서 4개 CSV를 찾지 못했습니다. 파일을 같은 폴더 또는 `data/`, `input/`, `inputs/` 폴더에 넣어주세요.")
        st.code("\n".join(EXPECTED_FILES.values()))
        return

    top_tabs = st.tabs(
        ["제품 별 데이터", "예약/수요 비교", "과거 Raw Data", "과거 신상품 조회", "카테고리 비교", "기준월 신상품"]
    )

    with top_tabs[0]:
        render_product_dashboard(base_date)

    with top_tabs[1]:
        render_reference_app_tab(base_date)

    with top_tabs[2]:
        for dataset in connected:
            render_raw_view(dataset, base_date)

    with top_tabs[3]:
        render_past_product_lookup(connected, base_date)

    with top_tabs[4]:
        render_category_drilldown(base_date)

    with top_tabs[5]:
        render_current_release_focus(connected, base_date)


if __name__ == "__main__":
    main()
