# tools/db_operaciones_cleaner.py
from __future__ import annotations

import re
from io import BytesIO
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st


# =========================
# Helpers
# =========================
def _safe_str(x) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x)

def _norm(s: str) -> str:
    s = _safe_str(s).strip().lower()
    s = s.replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u").replace("ñ","n")
    s = re.sub(r"\s+", " ", s)
    s = s.replace(".", "").replace("°","").replace("º","")
    return s

def _to_float(x) -> float:
    s = _safe_str(x).strip()
    if s in ("", "-", "–"):
        return float("nan")
    s = s.replace("$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return float("nan")

def _to_date(x):
    try:
        return pd.to_datetime(x, dayfirst=True, errors="coerce")
    except Exception:
        return pd.NaT

def _contains(col_norm: str, needles: List[str]) -> bool:
    return any(n in col_norm for n in needles)


# =========================
# Excel reading robust
# =========================
def detect_header_row(xls: pd.ExcelFile, sheet_name: str, max_scan_rows: int = 40) -> int:
    tmp = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=max_scan_rows)
    best_row, best_score = 0, -1

    wanted = [
        "especie", "referencia", "tipo operacion", "fecha operacion",
        "fecha liquidacion", "nro de operacion", "cantidad", "moneda", "precio", "importe"
    ]

    for i in range(len(tmp)):
        row_vals = [_norm(v) for v in tmp.iloc[i].tolist()]
        score = 0
        for w in wanted:
            if any(w == rv for rv in row_vals):
                score += 3
            elif any(w in rv for rv in row_vals):
                score += 1
        if score > best_score:
            best_score, best_row = score, i

    return best_row

def read_sheet_smart(xls: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    try:
        h = detect_header_row(xls, sheet_name)
        df = pd.read_excel(xls, sheet_name=sheet_name, header=h)
        if len(df.columns) and all(_norm(c).startswith("unnamed") for c in df.columns):
            df = pd.read_excel(xls, sheet_name=sheet_name, header=0)
        return df
    except Exception:
        return pd.read_excel(xls, sheet_name=sheet_name, header=0)

def pick_columns_fuzzy(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    cols_norm = {c: _norm(c) for c in df.columns}

    def find(needles: List[str], exact: Optional[str] = None) -> Optional[str]:
        if exact:
            ex = _norm(exact)
            for c, cn in cols_norm.items():
                if cn == ex:
                    return c
        for c, cn in cols_norm.items():
            if _contains(cn, needles):
                return c
        return None

    return {
        "especie": find(["especie"], exact="especie"),
        "referencia": find(["referencia"], exact="referencia"),
        "tipo_operacion": find(["tipo operacion", "tipooperacion", "tipo"], exact="tipo operacion"),
        "fecha_operacion": find(["fecha operacion", "fechaoperacion"], exact="fecha operacion"),
        "fecha_liquidacion": find(["fecha liquidacion", "fechaliquidacion"], exact="fecha liquidacion"),
        "nro_operacion": find(["nro de operacion", "nro operacion", "numero de operacion", "nro"], exact="nro de operacion"),
        "cantidad": find(["cantidad"], exact="cantidad"),
        "moneda": find(["moneda"], exact="moneda"),
        "precio": find(["precio"], exact="precio"),
        "importe": find(["importe"], exact="importe"),
    }

def standardize_df(df: pd.DataFrame) -> pd.DataFrame:
    m = pick_columns_fuzzy(df)

    out = pd.DataFrame()
    out["Especie"] = df[m["especie"]] if m["especie"] else ""
    out["Referencia"] = df[m["referencia"]] if m["referencia"] else ""
    out["TipoOperacion"] = df[m["tipo_operacion"]] if m["tipo_operacion"] else ""
    out["FechaOperacion"] = df[m["fecha_operacion"]].map(_to_date) if m["fecha_operacion"] else pd.NaT
    out["FechaLiquidacion"] = df[m["fecha_liquidacion"]].map(_to_date) if m["fecha_liquidacion"] else pd.NaT
    out["NroOperacion"] = df[m["nro_operacion"]] if m["nro_operacion"] else ""
    out["Cantidad"] = df[m["cantidad"]].map(_to_float) if m["cantidad"] else float("nan")
    out["Moneda"] = df[m["moneda"]] if m["moneda"] else ""
    out["Precio"] = df[m["precio"]].map(_to_float) if m["precio"] else float("nan")
    out["Importe"] = df[m["importe"]].map(_to_float) if m["importe"] else float("nan")

    for c in ["Especie", "Referencia", "TipoOperacion", "Moneda", "NroOperacion"]:
        out[c] = out[c].map(_safe_str).str.strip()

    out = out[~(
        out["Especie"].eq("") &
        out["Referencia"].eq("") &
        out["TipoOperacion"].eq("") &
        out["Moneda"].eq("") &
        out["NroOperacion"].eq("") &
        out["Importe"].isna()
    )].copy()

    return out

def add_quality_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Importe_faltante"] = out["Importe"].isna()
    out["Precio_faltante"] = out["Precio"].isna()
    out["Cantidad_faltante"] = out["Cantidad"].isna()
    out["Importe_calculable"] = out["Importe_faltante"] & (~out["Cantidad"].isna()) & (~out["Precio"].isna())
    out["Importe_sugerido"] = out["Cantidad"] * out["Precio"]

    out["Quality"] = "OK"
    out.loc[out["Importe_faltante"], "Quality"] = "FALTA_IMPORTE"
    out.loc[out["Importe_calculable"], "Quality"] = "FALTA_IMPORTE_PERO_CALCULABLE"
    return out

def group_sum(df: pd.DataFrame, by: List[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=by + ["Importe"])
    g = df.groupby(by, as_index=False)["Importe"].sum()
    return g.sort_values("Importe", ascending=False)

def to_excel_bytes(clean: pd.DataFrame, missing: pd.DataFrame, resumen: Dict[str, pd.DataFrame]) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        clean.to_excel(writer, sheet_name="Limpia", index=False)
        missing.to_excel(writer, sheet_name="Faltantes", index=False)
        for name, sdf in resumen.items():
            sdf.to_excel(writer, sheet_name=name[:31], index=False)
    return bio.getvalue()


# =========================
# Public entrypoint (Workbench)
# =========================
def render_db_operaciones_cleaner() -> None:
    """
    Llamá a esta función desde tu router/menu del Workbench.
    No usa set_page_config para no pisar la app principal.
    """
    st.header("DB Operaciones – Limpieza y análisis")
    st.caption("Detecta importes faltantes, resume por categorías y exporta Excel (limpia + faltantes).")

    up = st.file_uploader("Subí el Excel", type=["xlsx", "xls"], key="dbop_uploader")
    if not up:
        st.info("Subí un Excel para empezar.")
        return

    xls = pd.ExcelFile(up)
    sheet = st.selectbox("Hoja", options=["(todas)"] + xls.sheet_names, index=0, key="dbop_sheet")

    dfs = []
    if sheet == "(todas)":
        for sh in xls.sheet_names:
            df0 = read_sheet_smart(xls, sh)
            df0["__sheet__"] = sh
            dfs.append(df0)
    else:
        df0 = read_sheet_smart(xls, sheet)
        df0["__sheet__"] = sheet
        dfs.append(df0)

    raw = pd.concat(dfs, ignore_index=True)

    std = standardize_df(raw)
    std.insert(0, "OrigenHoja", raw["__sheet__"].values[: len(std)])  # defensivo
    std = add_quality_flags(std)

    st.subheader("Controles de limpieza")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        incluir_moneda_vacia = st.checkbox("Incluir filas Moneda vacía", value=True, key="dbop_moneda")
    with c2:
        excluir_sin_especie = st.checkbox("Excluir filas sin Especie", value=True, key="dbop_especie")
    with c3:
        imputar_importe = st.checkbox("Imputar Importe si es calculable (Cantidad×Precio)", value=False, key="dbop_imputar")

    work = std.copy()
    if not incluir_moneda_vacia:
        work = work[work["Moneda"].ne("")]
    if excluir_sin_especie:
        work = work[work["Especie"].ne("")]

    if imputar_importe:
        mask = work["Importe_calculable"]
        work.loc[mask, "Importe"] = work.loc[mask, "Importe_sugerido"]
        work = add_quality_flags(work)

    faltantes = work[work["Importe_faltante"]].copy()
    limpia = work[~work["Importe_faltante"]].copy()

    total_importe = float(limpia["Importe"].sum()) if len(limpia) else 0.0
    cant_total = len(work)
    cant_falt = len(faltantes)
    pct_falt = (cant_falt / cant_total * 100) if cant_total else 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Filas totales", f"{cant_total:,}")
    k2.metric("Filas sin Importe", f"{cant_falt:,}")
    k3.metric("% sin Importe", f"{pct_falt:,.2f}%")
    k4.metric("Suma Importe (solo limpias)", f"{total_importe:,.2f}")

    if cant_falt:
        st.warning("Hay filas SIN Importe. Revisá la pestaña Faltantes y exportá.")
    else:
        st.success("No hay filas sin Importe 🎉")

    res_tipo = group_sum(limpia, ["TipoOperacion"])
    res_mon = group_sum(limpia, ["Moneda"])
    res_especie = group_sum(limpia, ["Especie"])
    res_ref = group_sum(limpia, ["Referencia"])

    tabs = st.tabs(["Resumen", "Limpia", "Faltantes", "Diagnóstico", "Raw Preview"])

    with tabs[0]:
        a, b = st.columns(2)
        with a:
            st.subheader("Importe por Tipo Operación")
            st.dataframe(res_tipo, use_container_width=True, hide_index=True)
        with b:
            st.subheader("Importe por Moneda")
            st.dataframe(res_mon, use_container_width=True, hide_index=True)

        c, d = st.columns(2)
        with c:
            st.subheader("Top Especies por Importe")
            st.dataframe(res_especie.head(50), use_container_width=True, hide_index=True)
        with d:
            st.subheader("Top Referencias por Importe")
            st.dataframe(res_ref.head(50), use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Base limpia (con Importe)")
        st.dataframe(limpia.sort_values("FechaOperacion", ascending=False), use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Filas con Importe faltante")
        show_cols = [
            "OrigenHoja","Especie","Referencia","TipoOperacion","FechaOperacion","FechaLiquidacion",
            "NroOperacion","Cantidad","Moneda","Precio","Importe","Quality","Importe_calculable","Importe_sugerido"
        ]
        st.dataframe(faltantes[show_cols], use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader("Chequeos útiles")
        calc = work[work["Importe_calculable"]].copy()
        st.write("**Faltantes calculables (Cantidad×Precio):**", len(calc))
        st.dataframe(calc.head(200), use_container_width=True, hide_index=True)

        mv = work[work["Moneda"].eq("")].copy()
        st.write("**Moneda vacía:**", len(mv))
        st.dataframe(mv.head(200), use_container_width=True, hide_index=True)

        fn = work[work["FechaOperacion"].isna() | work["FechaLiquidacion"].isna()].copy()
        st.write("**Fecha nula:**", len(fn))
        st.dataframe(fn.head(200), use_container_width=True, hide_index=True)

    with tabs[4]:
        st.subheader("Raw preview (para debug)")
        st.dataframe(raw.head(50), use_container_width=True, hide_index=True)

    st.subheader("Exportar")
    excel_bytes = to_excel_bytes(
        limpia,
        faltantes,
        {
            "Resumen_TipoOp": res_tipo,
            "Resumen_Moneda": res_mon,
            "Resumen_Especie": res_especie,
            "Resumen_Referencia": res_ref,
        }
    )

    st.download_button(
        "Descargar Excel (Limpia + Faltantes + Resúmenes)",
        data=excel_bytes,
        file_name="db_operaciones_limpieza.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dbop_download",
    )
