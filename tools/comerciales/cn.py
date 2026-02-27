# fix_looker_excel_coma.py
# ---------------------------------------------------------
# Script LOCAL (Windows/Mac/Linux con GUI):
# - Pide el archivo Excel exportado de Looker (selector).
# - Convierte Neto/Gross a número real.
# - Guarda una copia *_coma.xlsx con formato numérico.
# ---------------------------------------------------------

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


NUM_COLS = ["Neto Agente", "Gross Agente"]


def pick_file_gui() -> str | None:
    """Selector GUI (tkinter). Devuelve path o None."""
    try:
        from tkinter import Tk, filedialog  # type: ignore
    except Exception:
        return None

    try:
        Tk().withdraw()
        return filedialog.askopenfilename(
            title="Seleccioná el Excel exportado de Looker",
            filetypes=[("Excel files", "*.xlsx *.xls")],
        )
    except Exception:
        return None


def pick_file_cli() -> str | None:
    """Fallback: pedir ruta por consola."""
    print("No pude abrir selector. Pegá la ruta del Excel (o Enter para cancelar):")
    p = input("> ").strip().strip('"')
    return p or None


def to_numeric_series(x: pd.Series) -> pd.Series:
    """
    Looker suele exportar con decimal punto (84.15).
    Esto lo fuerza a float aunque venga como texto.
    """
    s = x.astype(str).str.strip()
    s = s.replace({"": None, "None": None, "nan": None, "NaN": None})
    s = s.str.replace("\u00a0", "", regex=False).str.replace(" ", "", regex=False).str.replace("$", "", regex=False)
    return pd.to_numeric(s, errors="coerce")


def main() -> None:
    file_path = pick_file_gui()
    if not file_path:
        file_path = pick_file_cli()

    if not file_path:
        print("Cancelado.")
        return

    input_path = Path(file_path)
    if not input_path.exists():
        print(f"No existe: {input_path}")
        sys.exit(1)

    output_path = input_path.with_name(input_path.stem + "_coma.xlsx")

    df = pd.read_excel(input_path)
    df.columns = [str(c).strip() for c in df.columns]

    for c in NUM_COLS:
        if c in df.columns:
            df[c] = to_numeric_series(df[c])
        else:
            print(f"[WARN] No encontré columna '{c}'")

    # Guardar con formato numérico (Excel mostrará coma si tu configuración regional es ES/AR)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Consolidado")
        ws = writer.sheets["Consolidado"]

        for c in NUM_COLS:
            if c in df.columns:
                col_idx = df.columns.get_loc(c) + 1  # 1-based
                for col_cells in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=2):
                    for cell in col_cells:
                        cell.number_format = "#,##0.00"

    print(f"✅ Listo. Generado: {output_path}")


if __name__ == "__main__":
    main()
