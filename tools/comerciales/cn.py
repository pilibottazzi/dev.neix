# fix_looker_cn.py
# ---------------------------------------------------------
# Convierte export de Looker (decimales con ".") a Excel
# con números reales + formato con coma decimal (ES/AR).
# Pide el archivo por selector (ventanita).
# ---------------------------------------------------------

from __future__ import annotations

from pathlib import Path
from tkinter import Tk, filedialog

import pandas as pd


# Columnas a corregir (ajustá si cambian los nombres)
NUM_COLS = ["Neto Agente", "Gross Agente"]


def main() -> None:
    # Selector de archivo
    Tk().withdraw()
    file_path = filedialog.askopenfilename(
        title="Seleccioná el Excel exportado de Looker (CN)",
        filetypes=[("Excel files", "*.xlsx *.xls")],
    )

    if not file_path:
        print("No seleccionaste ningún archivo. Cancelado.")
        return

    input_path = Path(file_path)
    output_path = input_path.with_name(input_path.stem + "_coma.xlsx")

    # Leer Excel (Looker suele exportar números ya como num; si vinieran como texto, igual lo corrige)
    df = pd.read_excel(input_path)

    # Normalizar headers por si vienen con espacios
    df.columns = [str(c).strip() for c in df.columns]

    # Convertir columnas numéricas
    for c in NUM_COLS:
        if c in df.columns:
            # Si viniera texto con miles/moneda, limpiá mínimo
            # (en tu captura son valores simples tipo 84.15)
            df[c] = (
                df[c]
                .astype(str)
                .str.replace("\u00a0", "", regex=False)  # NBSP
                .str.replace(" ", "", regex=False)
                .str.replace("$", "", regex=False)
            )
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            print(f"[WARN] No encontré la columna '{c}' en el archivo.")

    # Guardar con formato numérico
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Consolidado")
        ws = writer.sheets["Consolidado"]

        # Formato numérico: Excel mostrará coma decimal con configuración ES/AR
        for c in NUM_COLS:
            if c in df.columns:
                col_idx = df.columns.get_loc(c) + 1  # 1-based
                for col_cells in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=2):
                    for cell in col_cells:
                        cell.number_format = "#,##0.00"

    print(f"✅ Listo. Archivo generado: {output_path}")


if __name__ == "__main__":
    main()
