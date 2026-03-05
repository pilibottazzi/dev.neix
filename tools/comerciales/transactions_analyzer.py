# tools/tenencias_to_db.py
from __future__ import annotations

import re
import calendar
import datetime as dt
from io import BytesIO
from typing import Optional, Tuple, Dict, List

import pandas as pd
import streamlit as st


# =========================
# 1) Meta desde nombre hoja
# =========================
MONTHS_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12
}

def parse_sheet_meta(sheet_name: str) -> Optional[Tuple[str, dt.date]]:
    """
    Espera nombres tipo: '904 Ene-26', '904 dic-25', '904 Ene 26', etc.
    Devuelve (comitente, fecha_fin_mes).
    """
    s = sheet_name.strip()

    # comitente al inicio
    m_com = re.match(r"^\s*(\d{3,4})\s+(.+?)\s*$", s)
    if not m_com:
        return None

    comitente = m_com.group(1)
    rest = m_com.group(2).strip()

    m = re.search(
        r"(?i)\b(ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)\b\W*(\d{2}|\d{4})\b",
        rest
    )
    if not m:
        return None

    mon = MONTHS_ES[m.group(1).lower()]
    year = int(m.group(2))
    if year < 100:
        year = 2000 + year

    last_day = calendar.monthrange(year, mon)[1]
    return comitente, dt.date(year, mon, last_day)


# =========================
# 2) Normalización
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
    return s

def _to_float(x) -> float:
    s = _safe_str(x).strip()
    if s in ("", "-", "–"):
        return float("nan")
    s = s.replace("%", "").replace("$", "").replace(" ", "")
    # 1.234,56 -> 1234.56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return float("nan")

def _find_col(df: pd.DataFrame, wanted: List[str]) -> Optional[str]:
    cols = {c: _norm(c) for c in df.columns}
    wanted_norm = [_norm(w) for w in wanted]
    for w in wanted_norm:
        for c, cn in cols.items():
            if cn == w:
                return c
    return None


# =========================
# 3) Lectura robusta de hoja
# =========================
def detect_header_row_df(tmp: pd.DataFrame, max_scan_rows: int = 30) -> int:
    """
    tmp: DataFrame leído con header=None.
    Busca fila donde aparezcan Especie/Cantidad/Precio/Importe/Part.
    """
    wanted = ["especie", "cantidad", "precio", "importe", "part", "part."]
    best_i, best_score = 0, -1

    n = min(max_scan_rows, len(tmp))
    for i in range(n):
        row = [_norm(v) for v in tmp.iloc[i].tolist()]
        score = 0
        for w in wanted:
            if any(w == rv for rv in row):
                score += 3
            elif any(w in rv for rv in row):
                score += 1
        if score > best_score:
            best_score, best_i = score, i

    return best_i

def read_sheet_smart(xls: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    """
    Lee hoja de tenencias aunque tenga filas arriba / header corrido.
    """
    try:
        tmp = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=40)
        h = detect_header_row_df(tmp)
        df = pd.read_excel(xls, sheet_name=sheet_name, header=h)
        # si quedó todo Unnamed, fallback a header=0
        if len(df.columns) and all(_norm(c).startswith("unnamed") for c in df.columns):
            df = pd.read_excel(xls, sheet_name=sheet_name, header=0)
        return df
    except Exception:
        return pd.read_excel(xls, sheet_name=sheet_name, header=0)


# =========================
# 4) Clasificación REAL (hacia atrás, siguiendo el Excel)
# =========================
TOTAL_LABELS = {
    "TOTAL ACCIONES": "Acciones",
    "TOTAL TITULOS PUBLICOS": "Titulos Publicos",
    "TOTAL TITULOS PÚBLICOS": "Titulos Publicos",
    "TOTAL OBLIGACIONES NEGOCIABLES": "ON",
    "TOTAL FCI": "FCI",
    "TOTAL CUENTA CORRIENTE": "Cuenta Corriente",
}
STOP_ROWS = {"TOTAL POSICION"}  # si aparece


def tenencias_sheet_to_rows(
    xls: pd.ExcelFile,
    sheet: str,
    comitente: str,
    fecha_cierre: dt.date
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Devuelve:
      - instrumentos_db: filas de instrumentos (sin filas TOTAL)
      - totales_db: filas TOTAL (TOTAL ACCIONES, TOTAL CUENTA CORRIENTE, etc.)
    Clasifica “hacia atrás” siguiendo el Excel:
      [instrumentos ...]  -> (aparece TOTAL X) => esos instrumentos son clase X
    """
    raw = read_sheet_smart(xls, sheet)

    col_especie = _find_col(raw, ["Especie"]) or raw.columns[0]
    col_cant = _find_col(raw, ["Cantidad"])
    col_precio = _find_col(raw, ["Precio"])
    col_importe = _find_col(raw, ["Importe"])
    col_part = _find_col(raw, ["Part.", "Part"])

    df = pd.DataFrame({
        "especie": raw[col_especie].map(_safe_str).str.strip(),
        "cantidad": raw[col_cant].map(_to_float) if col_cant else float("nan"),
        "precio": raw[col_precio].map(_to_float) if col_precio else float("nan"),
        "importe": raw[col_importe].map(_to_float) if col_importe else float("nan"),
        "part": raw[col_part].map(_to_float) if col_part else float("nan"),
    })

    df = df[df["especie"].ne("")].copy()

    pending_rows: List[Dict] = []
    out_instruments: List[Dict] = []
    out_totals: List[Dict] = []

    def flush_pending_as(clase: str) -> None:
        nonlocal pending_rows, out_instruments
        if not pending_rows:
            return
        for r in pending_rows:
            r["clase"] = clase
            out_instruments.append(r)
        pending_rows = []

    for _, row in df.iterrows():
        esp = _safe_str(row["especie"]).strip()
        esp_u = esp.upper().strip()

        if esp_u in STOP_ROWS:
            break

        # TOTAL mapeado: clasifica hacia atrás + guarda total
        if esp_u in TOTAL_LABELS:
            clase_total = TOTAL_LABELS[esp_u]
            flush_pending_as(clase_total)

            out_totals.append({
                "comitente": comitente,
                "fecha_cierre": fecha_cierre,
                "total_tipo": clase_total,     # Acciones / Titulos Publicos / Cuenta Corriente / ...
                "label": esp_u,                # texto exacto
                "importe_total": row["importe"],
                "part_total": row["part"],
            })
            continue

        # TOTAL no mapeado: corta bloque, no guarda
        if esp_u.startswith("TOTAL "):
            flush_pending_as("SinClasificar")
            continue

        # fila normal -> acumular
        pending_rows.append({
            "comitente": comitente,
            "fecha_cierre": fecha_cierre,
            "clase": "SinClasificar",  # se define al flush
            "especie": esp,
            "cantidad": row["cantidad"],
            "precio": row["precio"],
            "importe": row["importe"],
            "part": row["part"],
        })

    # si quedó algo sin TOTAL al final, va a SinClasificar
    flush_pending_as("SinClasificar")

    instrumentos_db = pd.DataFrame(out_instruments)
    totales_db = pd.DataFrame(out_totals)
    return instrumentos_db, totales_db


# =========================
# 5) Comparación Mes vs Mes (anterior vs nuevo)
# =========================
def _snapshot_totales_por_comitente_fecha(db: pd.DataFrame) -> pd.DataFrame:
    """
    Snapshot total por comitente y fecha_cierre.
    """
    if db.empty:
        return pd.DataFrame(columns=["comitente", "fecha_cierre", "total"])
    d = db.copy()
    d["fecha_cierre"] = pd.to_datetime(d["fecha_cierre"])
    snap = (
        d.groupby(["comitente", "fecha_cierre"], as_index=False)
         .agg(total=("importe", "sum"))
         .sort_values(["comitente", "fecha_cierre"])
    )
    return snap

def make_mes_a_mes(
    db: pd.DataFrame,
    fecha_prev: dt.date,
    fecha_new: dt.date
) -> pd.DataFrame:
    """
    Devuelve ganancia/pérdida por comitente entre dos cierres:
      diff = total(fecha_new) - total(fecha_prev)
    """
    snap = _snapshot_totales_por_comitente_fecha(db)

    if snap.empty:
        return pd.DataFrame(columns=["comitente", "total_prev", "total_new", "diferencia"])

    fp = pd.to_datetime(fecha_prev)
    fn = pd.to_datetime(fecha_new)

    prev = snap[snap["fecha_cierre"].eq(fp)].copy().rename(columns={"total": "total_prev"})
    new  = snap[snap["fecha_cierre"].eq(fn)].copy().rename(columns={"total": "total_new"})

    out = prev.merge(new[["comitente", "total_new"]], on="comitente", how="outer")
    out["total_prev"] = out["total_prev"].fillna(0.0)
    out["total_new"] = out["total_new"].fillna(0.0)
    out["diferencia"] = out["total_new"] - out["total_prev"]

    out = out.sort_values("diferencia", ascending=False)
    return out

def make_mes_a_mes_detalle(
    db: pd.DataFrame,
    fecha_prev: dt.date,
    fecha_new: dt.date,
    nivel: str = "especie"  # "especie" o "clase"
) -> pd.DataFrame:
    """
    Detalle por comitente:
      - nivel="especie": diff por especie
      - nivel="clase": diff por clase
    """
    if db.empty:
        cols = ["comitente", nivel, "importe_prev", "importe_new", "diferencia"]
        return pd.DataFrame(columns=cols)

    d = db.copy()
    d["fecha_cierre"] = pd.to_datetime(d["fecha_cierre"])
    fp = pd.to_datetime(fecha_prev)
    fn = pd.to_datetime(fecha_new)

    key_cols = ["comitente", nivel]

    prev = (
        d[d["fecha_cierre"].eq(fp)]
        .groupby(key_cols, as_index=False)
        .agg(importe_prev=("importe", "sum"))
    )
    new = (
        d[d["fecha_cierre"].eq(fn)]
        .groupby(key_cols, as_index=False)
        .agg(importe_new=("importe", "sum"))
    )

    out = prev.merge(new, on=key_cols, how="outer")
    out["importe_prev"] = out["importe_prev"].fillna(0.0)
    out["importe_new"] = out["importe_new"].fillna(0.0)
    out["diferencia"] = out["importe_new"] - out["importe_prev"]

    out = out.sort_values(["comitente", "diferencia"], ascending=[True, False])
    return out


def make_total_cc_anual(totales_db: pd.DataFrame) -> pd.DataFrame:
    """
    Tabla anual: TOTAL CUENTA CORRIENTE por comitente y año (por si la querés igual).
    """
    if totales_db.empty:
        return pd.DataFrame(columns=["comitente", "anio", "importe_total_cc"])

    t = totales_db.copy()
    t["anio"] = pd.to_datetime(t["fecha_cierre"]).dt.year

    cc = t[t["total_tipo"].eq("Cuenta Corriente")].copy()
    out = (
        cc.groupby(["comitente", "anio"], as_index=False)
          .agg(importe_total_cc=("importe_total", "sum"))
          .sort_values(["comitente", "anio"])
    )
    return out


def to_excel_bytes(base: pd.DataFrame, sheets: Dict[str, pd.DataFrame]) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        base.to_excel(writer, sheet_name="tenencias_db", index=False)
        for name, sdf in sheets.items():
            sdf.to_excel(writer, sheet_name=name[:31], index=False)
    return bio.getvalue()


# =========================
# 6) Entry point Workbench
# =========================
def render_tenencias_to_db() -> None:
    st.header("Tenencias valorizadas → Base tipo DB + Mes a Mes")
    st.caption("Convierte el Excel (hojas: comitente + mes) en una base y calcula variación mes anterior vs mes nuevo.")

    uploaded = st.file_uploader("Subí el Excel de tenencias", type=["xlsx", "xls"], key="ten_up")
    if not uploaded:
        st.info("Subí el archivo para comenzar.")
        return

    xls = pd.ExcelFile(uploaded)

    # detectar hojas con meta
    meta = []
    for sh in xls.sheet_names:
        m = parse_sheet_meta(sh)
        if m:
            com, fecha = m
            meta.append({"sheet": sh, "comitente": com, "fecha_cierre": fecha})

    meta_df = pd.DataFrame(meta)
    if meta_df.empty:
        st.error("No pude interpretar nombres de hojas. Ejemplos válidos: '904 Ene-26', '904 Dic-25'.")
        return

    meta_df = meta_df.sort_values(["comitente", "fecha_cierre"])
    st.subheader("Hojas detectadas")
    st.dataframe(meta_df, use_container_width=True, hide_index=True)

    comitentes = sorted(meta_df["comitente"].unique())
    sel_com = st.multiselect("Comitentes a procesar", comitentes, default=comitentes, key="ten_coms")

    only_latest = st.checkbox("Solo último mes por comitente (para base)", value=False, key="ten_latest")

    colA, colB = st.columns([1, 2])
    with colA:
        run = st.button("Procesar", type="primary", key="ten_run")
    with colB:
        st.caption("Tip: si hay muchas hojas, probá con 1 comitente para validar lectura y clasificación.")

    if not run:
        return

    work = meta_df[meta_df["comitente"].isin(sel_com)].copy()
    if only_latest:
        work = work.sort_values(["comitente", "fecha_cierre"]).groupby("comitente", as_index=False).tail(1)

    out_instruments = []
    out_totals = []
    errores = []

    for r in work.itertuples(index=False):
        try:
            inst_db, tot_db = tenencias_sheet_to_rows(xls, r.sheet, r.comitente, r.fecha_cierre)
            if inst_db is None or inst_db.empty:
                errores.append(f"{r.sheet}: sin filas útiles (revisar formato)")
            else:
                out_instruments.append(inst_db)
            if tot_db is not None and not tot_db.empty:
                out_totals.append(tot_db)
        except Exception as e:
            errores.append(f"{r.sheet}: {e}")

    if errores:
        st.warning("Algunas hojas no pudieron procesarse:")
        for e in errores[:15]:
            st.write("•", e)
        if len(errores) > 15:
            st.write(f"… y {len(errores)-15} más.")

    if not out_instruments:
        st.error("No se generaron filas. Probá con un comitente específico para debug.")
        return

    db = pd.concat(out_instruments, ignore_index=True)
    totales = pd.concat(out_totals, ignore_index=True) if out_totals else pd.DataFrame(
        columns=["comitente", "fecha_cierre", "total_tipo", "label", "importe_total", "part_total"]
    )

    # -----------------
    # Mes a Mes (prev vs new)
    # -----------------
    fechas_disponibles = sorted({pd.to_datetime(x).date() for x in meta_df["fecha_cierre"].tolist()})
    if len(fechas_disponibles) >= 2:
        default_prev = fechas_disponibles[-2]
        default_new = fechas_disponibles[-1]
    else:
        default_prev = fechas_disponibles[0]
        default_new = fechas_disponibles[0]

    st.subheader("Comparación Mes a Mes")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        fecha_prev = st.selectbox("Mes anterior (cierre)", fechas_disponibles, index=max(0, len(fechas_disponibles)-2), key="mm_prev")
    with c2:
        fecha_new = st.selectbox("Mes nuevo (cierre)", fechas_disponibles, index=max(0, len(fechas_disponibles)-1), key="mm_new")
    with c3:
        nivel_detalle = st.radio("Detalle", ["especie", "clase"], horizontal=True, index=0, key="mm_nivel")

    mm = make_mes_a_mes(db, fecha_prev=fecha_prev, fecha_new=fecha_new)
    mm_det = make_mes_a_mes_detalle(db, fecha_prev=fecha_prev, fecha_new=fecha_new, nivel=nivel_detalle)

    gan_total = float(mm["diferencia"].sum()) if not mm.empty else 0.0
    st.metric(f"Variación total (nuevo - anterior) [{fecha_new} vs {fecha_prev}]", f"{gan_total:,.2f}")

    # Resumen por clase (por fecha)
    resumen_clase = (
        db.groupby(["comitente", "fecha_cierre", "clase"], as_index=False)
          .agg(importe=("importe", "sum"), instrumentos=("especie", "count"))
          .sort_values(["comitente", "fecha_cierre", "importe"], ascending=[True, True, False])
    )

    # Total CC anual (por si querés seguir esa idea)
    total_cc_anual = make_total_cc_anual(totales)

    # -----------------
    # Tabs
    # -----------------
    t1, t2, t3, t4, t5, t6 = st.tabs([
        "Base",
        "Resumen por clase",
        "Totales",
        "Mes a Mes (comitente)",
        f"Detalle M/M ({nivel_detalle})",
        "TOTAL CC anual",
    ])

    with t1:
        st.dataframe(db, use_container_width=True, hide_index=True)

    with t2:
        st.dataframe(resumen_clase, use_container_width=True, hide_index=True)

    with t3:
        st.dataframe(totales, use_container_width=True, hide_index=True)

    with t4:
        st.subheader("Ganancia/Pérdida por comitente (mes nuevo - mes anterior)")
        st.dataframe(mm, use_container_width=True, hide_index=True)

    with t5:
        st.subheader(f"Detalle por {nivel_detalle} (mes nuevo - mes anterior)")
        # para no explotar la UI si es enorme
        st.dataframe(mm_det, use_container_width=True, hide_index=True, height=520)

    with t6:
        st.dataframe(total_cc_anual, use_container_width=True, hide_index=True)

    # -----------------
    # Export
    # -----------------
    excel_bytes = to_excel_bytes(
        db,
        {
            "resumen_clase": resumen_clase,
            "totales_db": totales,
            "MM_COMITENTE": mm,
            f"MM_DET_{nivel_detalle.upper()}": mm_det,
            "TOTAL_CC_ANUAL": total_cc_anual,
        }
    )

    st.download_button(
        "Descargar Excel (base + resúmenes + mes a mes)",
        data=excel_bytes,
        file_name="tenencias_base_datos_mes_a_mes.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="ten_dl",
    )


# =========================
# 7) Workbench expected entrypoint
# =========================
def render():
    """Entry point estándar para NEIX Workbench."""
    return render_tenencias_to_db()
