import re
import time
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, current_app
)
from db import get_conn, db_lock

admin_bp = Blueprint("admin", __name__)

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
