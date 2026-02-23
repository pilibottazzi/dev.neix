cols1 = cartera_data[0]
ley_i = cols1.index("Ley") if "Ley" in cols1 else None
iss_i = cols1.index("Issuer") if "Issuer" in cols1 else None

style_cmds = [
    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 8.6),
    ("FONTSIZE", (0, 1), (-1, -1), 8.0),  # ⬅️ un toque más chico
    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ("BOX", (0, 0), (-1, -1), 0.6, colors.lightgrey),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ("TOPPADDING", (0, 0), (-1, 0), 6),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ("TOPPADDING", (0, 1), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
    ("ALIGN", (0, 0), (0, -1), "LEFT"),
    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
]

# ⬇️ Texto a la izquierda para columnas “Ley” e “Issuer”
if ley_i is not None:
    style_cmds.append(("ALIGN", (ley_i, 1), (ley_i, -1), "LEFT"))
if iss_i is not None:
    style_cmds.append(("ALIGN", (iss_i, 1), (iss_i, -1), "LEFT"))

t1.setStyle(TableStyle(style_cmds))
