import re
import time
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, current_app
)
from db import get_conn, db_lock

# --------- IMPORTS que quizá no tengas arriba ---------
from flask import request, render_template, redirect, url_for, flash, session, jsonify
from datetime import datetime

# Si no están ya:
from . import admin_bp
from db import get_conn, db_lock


def _strip(s):
    return (s or "").strip()


# ---------- FORMULARIO WEB ----------
@admin_bp.route("/admin/preguntas/nueva", methods=["GET", "POST"])
def subir_pregunta():
    # opcional: exigir login
    if not session.get("usuario_id"):
        # adapta si tu login es otro
        return redirect(url_for("auth.login_form"))

    if request.method == "POST":
        pregunta     = _strip(request.form.get("pregunta"))
        categoria    = _strip(request.form.get("categoria")) or "General"
        dificultad   = _strip(request.form.get("dificultad")) or "Media"
        ruta_audio   = _strip(request.form.get("ruta_audio")) or None
        ruta_imagen  = _strip(request.form.get("ruta_imagen")) or None
        es_encuesta  = request.form.get("es_encuesta") == "on"

        # opciones de respuesta
        respuestas_raw = request.form.getlist("respuestas[]")
        respuestas = [r.strip() for r in respuestas_raw if r and r.strip()]

        # índice de la correcta (solo si no es encuesta)
        correcta_idx = request.form.get("correcta")

        # Validaciones mínimas
        if not pregunta:
            flash("Falta el texto de la pregunta.", "error")
            return render_template("admin_subir_pregunta.html")

        if len(respuestas) < 2:
            flash("Debes incluir al menos 2 opciones.", "error")
            return render_template("admin_subir_pregunta.html",
                                   pregunta=pregunta, categoria=categoria,
                                   dificultad=dificultad, ruta_audio=ruta_audio,
                                   ruta_imagen=ruta_imagen, es_encuesta=es_encuesta,
                                   respuestas=respuestas)

        if not es_encuesta:
            if correcta_idx is None:
                flash("Selecciona una opción correcta.", "error")
                return render_template("admin_subir_pregunta.html",
                                       pregunta=pregunta, categoria=categoria,
                                       dificultad=dificultad, ruta_audio=ruta_audio,
                                       ruta_imagen=ruta_imagen, es_encuesta=es_encuesta,
                                       respuestas=respuestas)
            try:
                correcta_idx = int(correcta_idx)
            except ValueError:
                correcta_idx = -1
            if not (0 <= correcta_idx < len(respuestas)):
                flash("Índice de respuesta correcta inválido.", "error")
                return render_template("admin_subir_pregunta.html",
                                       pregunta=pregunta, categoria=categoria,
                                       dificultad=dificultad, ruta_audio=ruta_audio,
                                       ruta_imagen=ruta_imagen, es_encuesta=es_encuesta,
                                       respuestas=respuestas)

        # Inserción en DB
        with db_lock:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO Preguntas
                    (pregunta, categoria, dificultad, fecha_creacion, fecha_mostrada, ruta_audio, ruta_imagen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    pregunta, categoria, dificultad,
                    datetime.now().isoformat(timespec="seconds"),
                    None, ruta_audio, ruta_imagen
                ))
                id_pregunta = cur.lastrowid

                for i, texto in enumerate(respuestas):
                    correcta = 0 if es_encuesta else int(i == correcta_idx)
                    cur.execute("""
                        INSERT INTO Respuestas (id_pregunta, respuesta, correcta)
                        VALUES (?, ?, ?)
                    """, (id_pregunta, texto, correcta))

                conn.commit()

        flash("✅ Pregunta creada correctamente.", "success")
        return redirect(url_for("admin.subir_pregunta"))

    # GET
    return render_template("admin_subir_pregunta.html")


# ---------- API JSON (opcional) ----------
# POST /admin/preguntas
# Body (JSON):
# {
#   "pregunta": "Texto",
#   "categoria": "General",
#   "dificultad": "Media",
#   "es_encuesta": true,             # o false
#   "ruta_audio": null,
#   "ruta_imagen": null,
#   "opciones": ["A", "B", "C", "D"],
#   "correcta_idx": 2                # requerido SOLO si es_encuesta=false
# }
@admin_bp.route("/admin/preguntas", methods=["POST"])
def subir_pregunta_json():
    data = request.get_json(silent=True) or {}
    pregunta   = _strip(data.get("pregunta"))
    categoria  = _strip(data.get("categoria")) or "General"
    dificultad = _strip(data.get("dificultad")) or "Media"
    ruta_audio = _strip(data.get("ruta_audio")) or None
    ruta_imagen= _strip(data.get("ruta_imagen")) or None
    es_encuesta = bool(data.get("es_encuesta"))
    opciones    = [ _strip(x) for x in (data.get("opciones") or []) if _strip(x) ]
    correcta_idx = data.get("correcta_idx", None)

    if not pregunta or len(opciones) < 2:
        return jsonify({"ok": False, "error": "Pregunta u opciones inválidas (mínimo 2)."}), 400
    if not es_encuesta:
        if correcta_idx is None or not isinstance(correcta_idx, int) or not (0 <= correcta_idx < len(opciones)):
            return jsonify({"ok": False, "error": "correcta_idx inválido."}), 400

    with db_lock:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO Preguntas
                (pregunta, categoria, dificultad, fecha_creacion, fecha_mostrada, ruta_audio, ruta_imagen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                pregunta, categoria, dificultad,
                datetime.now().isoformat(timespec="seconds"),
                None, ruta_audio, ruta_imagen
            ))
            id_pregunta = cur.lastrowid

            for i, texto in enumerate(opciones):
                correcta = 0 if es_encuesta else int(i == correcta_idx)
                cur.execute("""
                    INSERT INTO Respuestas (id_pregunta, respuesta, correcta)
                    VALUES (?, ?, ?)
                """, (id_pregunta, texto, correcta))
            conn.commit()

    return jsonify({"ok": True, "id_pregunta": id_pregunta})


# --- Reglas de seguridad: solo lectura por defecto ---
_FORBIDDEN_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|vacuum|reindex|grant|revoke|begin|commit|rollback|savepoint|release|analyze)\b",
    re.IGNORECASE
)

def _is_readonly_sql(sql: str) -> bool:
    """Permite SELECT / WITH / EXPLAIN (una sola sentencia)."""
    if not sql:
        return False
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].rstrip()
    if ";" in s:
        return False  # bloquea múltiples sentencias
    if _FORBIDDEN_WRITE.search(s):
        return False
    first = s.split(None, 1)[0].lower()
    return first in {"select", "with", "explain"}

# --------- PANEL (login + SQL en la misma vista) ---------
@admin_bp.route("/admin/login", methods=["GET", "POST"])
def login_admin():
    if request.method == "GET":
        if session.get("is_admin"):
            return redirect(url_for("admin.panel_admin"))
        return render_template("panel_login.html")

    password = request.form.get("admin_password", "")
    if password == current_app.config.get("ADMIN_PASSWORD"):
        session["is_admin"] = True
        flash("Has accedido al modo administrador.", "success")
        return redirect(url_for("admin.panel_admin"))
    flash("Contraseña incorrecta.", "error")
    return redirect(url_for("admin.login_admin"))

@admin_bp.route("/admin/logout", methods=["GET", "POST"])
def logout_admin():
    session.pop("is_admin", None)
    flash("Has salido del modo administrador.", "info")
    return redirect(url_for("index"))

@admin_bp.route("/admin", methods=["GET", "POST"])
def panel_admin():
    # Requiere sesión admin
    if not session.get("is_admin"):
        return redirect(url_for("admin.login_admin"))

    # Defaults del formulario
    default_sql = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    sql = request.form.get("sql", default_sql)
    limit = request.form.get("limit", "200")
    allow_write = request.form.get("allow_write") == "on"

    try:
        limit = max(1, min(int(limit), 5000))
    except Exception:
        limit = 200

    columns, rows = [], []
    elapsed_ms = None
    message = None
    error = None

    if request.method == "POST":
        try:
            t0 = time.perf_counter()
            with db_lock:
                with get_conn() as conn:
                    cur = conn.cursor()
                    if allow_write:
                        # Ejecuta script completo (PELIGRO en producción)
                        cur.executescript(sql)
                        conn.commit()
                        message = "Script ejecutado correctamente."
                        try:
                            message += f" (rowcount: {cur.rowcount})"
                        except Exception:
                            pass
                    else:
                        # Solo lectura segura
                        if not _is_readonly_sql(sql):
                            raise ValueError(
                                "Solo se permiten SELECT/WITH/EXPLAIN en modo lectura (una sola sentencia)."
                            )
                        cur.execute(sql)
                        if cur.description:
                            columns = [d[0] for d in cur.description]
                            rows = cur.fetchmany(limit)
                        else:
                            columns, rows = [], []
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as ex:
            error = str(ex)

    return render_template(
        "panel.html",  # tu panel ahora es el ejecutor SQL
        sql=sql,
        columns=columns,
        rows=rows,
        limit=limit,
        allow_write=allow_write,
        elapsed_ms=elapsed_ms,
        message=message,
        error=error,
    )
