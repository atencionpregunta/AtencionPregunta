# encuestas_whatsapp_formato_opcion.py
# -*- coding: utf-8 -*-
import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path
from datetime import datetime

# -------------------- Utilidades nombres/archivos --------------------
def slugify(text, maxlen=60):
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch)
        elif ch in " -._":
            out.append("_")
    s = "".join(out).strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    return s[:maxlen] or "whatsapp_chat"

def next_available(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    n = 1
    while True:
        cand = parent / f"{stem}-v{n}{suffix}"
        if not cand.exists():
            return cand
        n += 1

# -------------------- Patrones WhatsApp / Encuestas --------------------
# "27/1/23, 10:25 - Nombre: Mensaje"
PAT_MSG = re.compile(
    r"""^
    (\d{1,2}\/\d{1,2}\/\d{2,4})
    [,\s]*
    (\d{1,2}:\d{2})
    \s*-\s*
    ([^:]+)
    :\s*
    (.*)$
    """, re.VERBOSE
)

def es_inicio_mensaje(linea: str) -> bool:
    return bool(PAT_MSG.match(linea))

def trocea_mensaje(linea: str):
    m = PAT_MSG.match(linea)
    if not m:
        return None
    fecha, hora, autor, msg = m.groups()
    return fecha, hora, autor.strip(), (msg or "").strip()

# Tu formato:
# L0: "...: ENCUESTA:"
# L1: "🚨 ATENCIÓN PREGUNTA: ¿...?"
# L2+: "OPCIÓN: Texto (N votos)"
PAT_ENCUESTA_TAG = re.compile(r"(?i)^\s*ENCUESTA\s*:\s*$")
PAT_PREGUNTA_LINE = re.compile(r"(?i)^\s*(?:🚨\s*)?(?:ATENCI[ÓO]N\s+PREGUNTA\s*:\s*)?(.*\S)\s*$")
PAT_OPCION = re.compile(r"(?i)^\s*OPCI[ÓO]N\s*:\s*(.+?)(?:\s*\(\s*.*?voto?s?\s*\))?\s*$")

def parse_fecha_iso(fecha: str, hora: str) -> str:
    dd, mm, aa = fecha.split("/")
    if len(aa) == 2:
        aa = "20" + aa
    try:
        dt = datetime.strptime(f"{aa}-{mm.zfill(2)}-{dd.zfill(2)} {hora}", "%Y-%m-%d %H:%M")
        return dt.isoformat(timespec="minutes")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")

# -------------------- Localización del TXT --------------------
def elegir_por_dialogo() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        ruta = filedialog.askopenfilename(
            title="Elige el TXT exportado de WhatsApp",
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")]
        )
        return Path(ruta) if ruta else None
    except Exception:
        return None

def resolver_ruta_txt(argv_path: str | None) -> Path | None:
    if argv_path:
        p = Path(argv_path).expanduser()
        if p.exists():
            return p
    candidatos = sorted(Path(".").glob("WhatsApp Chat*.txt"),
                        key=lambda x: x.stat().st_mtime if x.exists() else 0,
                        reverse=True)
    if candidatos:
        return candidatos[0]
    dlg = elegir_por_dialogo()
    if dlg and dlg.exists():
        return dlg
    alt = Path("chat.txt")
    return alt if alt.exists() else None

# -------------------- Parser específico del formato --------------------
def parsear_chat_a_encuestas(ruta_txt: Path):
    with ruta_txt.open("r", encoding="utf-8-sig", errors="ignore") as f:
        lineas = f.readlines()

    preguntas_rows, respuestas_rows = [], []
    id_p, id_r = 1, 1

    i, n = 0, len(lineas)
    while i < n:
        linea = lineas[i].rstrip("\n")
        trozos = trocea_mensaje(linea)

        if trozos:
            fecha, hora, autor, msg = trozos
            # ¿Mensaje "ENCUESTA:" exacto?
            if PAT_ENCUESTA_TAG.match(msg):
                fecha_creacion = parse_fecha_iso(fecha, hora)

                # Siguiente línea -> pregunta
                j = i + 1
                if j < n and not es_inicio_mensaje(lineas[j]):
                    preg_line = lineas[j].strip()
                    m_preg = PAT_PREGUNTA_LINE.match(preg_line)
                    pregunta_txt = (m_preg.group(1).strip() if m_preg else preg_line)
                    j += 1
                else:
                    i += 1
                    continue

                # Opciones "OPCIÓN: ..."
                opciones = []
                while j < n and not es_inicio_mensaje(lineas[j]):
                    t = lineas[j].strip()
                    if not t:
                        j += 1; continue
                    m_opt = PAT_OPCION.match(t)
                    if m_opt:
                        op_txt = m_opt.group(1).strip().replace("\u200e", "").replace("\u200f", "")
                        op_txt = op_txt.strip()
                        if op_txt:
                            opciones.append(op_txt)
                        j += 1
                    else:
                        break

                if pregunta_txt and len(opciones) >= 2:
                    preguntas_rows.append({
                        "id": id_p,
                        "pregunta": pregunta_txt,
                        "categoria": "Encuestas WhatsApp",
                        "dificultad": "Media",
                        "fecha_creacion": fecha_creacion,
                        "fecha_mostrada": "",
                        "ruta_audio": "",
                        "ruta_imagen": ""
                    })
                    for op in opciones:
                        respuestas_rows.append({
                            "id": id_r,
                            "id_pregunta": id_p,
                            "respuesta": op,
                            "correcta": False
                        })
                        id_r += 1
                    id_p += 1

                i = j
                continue

        i += 1

    return preguntas_rows, respuestas_rows

# -------------------- Guardado CSV --------------------
def _clean_txt(s: str) -> str:
    if s is None:
        return ""
    # quita marcas invisibles frecuentes y normaliza
    s = s.replace("\u200e", "").replace("\u200f", "").replace("\ufeff", "")
    return s.strip()

def guardar_csv(pregs, resps, base_name: str):
    from pathlib import Path
    import csv

    out_dir = Path("salida"); out_dir.mkdir(exist_ok=True)
    base = slugify(base_name)
    preg_csv = next_available(out_dir / f"{base}_preguntas.csv")
    resp_csv = next_available(out_dir / f"{base}_respuestas.csv")

    # CSV para Excel ES: UTF-8 con BOM + separador ';'
    with open(preg_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "id","pregunta","categoria","dificultad",
                "fecha_creacion","fecha_mostrada","ruta_audio","ruta_imagen"
            ],
            delimiter=";", quoting=csv.QUOTE_MINIMAL
        )
        w.writeheader()
        for r in pregs:
            r = {k: _clean_txt(v) if isinstance(v, str) else v for k, v in r.items()}
            w.writerow(r)

    with open(resp_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["id","id_pregunta","respuesta","correcta"],
            delimiter=";", quoting=csv.QUOTE_MINIMAL
        )
        w.writeheader()
        for r in resps:
            r = {k: _clean_txt(v) if isinstance(v, str) else v for k, v in r.items()}
            w.writerow(r)

    return preg_csv, resp_csv


# -------------------- CLI --------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Extrae encuestas (ENCUESTA:/OPCIÓN:) de un TXT de WhatsApp y genera CSV."
    )
    p.add_argument("txt", nargs="?", help="Ruta al TXT (opcional). Si no, busca 'WhatsApp Chat*.txt' o 'chat.txt'.")
    return p.parse_args()

def main():
    args = parse_args()
    ruta = resolver_ruta_txt(args.txt)
    if not ruta:
        print("❌ No se encontró el TXT. Pásalo por argumento o renómbralo a 'chat.txt' en la carpeta del script.")
        sys.exit(1)

    print(f"Usando TXT: {ruta.resolve()}")
    preguntas, respuestas = parsear_chat_a_encuestas(ruta)
    print(f"→ Extraídas {len(preguntas)} encuestas con {len(respuestas)} opciones")

    preg_csv, resp_csv = guardar_csv(preguntas, respuestas, base_name=ruta.stem)
    print(f"✔ CSV:\n  {preg_csv}\n  {resp_csv}")

if __name__ == "__main__":
    main()
