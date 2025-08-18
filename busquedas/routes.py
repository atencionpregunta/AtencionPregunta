# busquedas/routes.py
from flask import Blueprint, request, jsonify, session, abort, render_template
from db import get_conn, db_lock
from utils import email_puede_buscar, get_id_grupo_actual

busquedas_bp = Blueprint("busquedas", __name__, url_prefix="/busquedas")

def _check_perm():
    # 1) Debe haber sesión
    usuario_email = session.get("usuario_email")
    if not usuario_email:
        abort(401)  # no logueado

    # 2) El email debe estar permitido (allowlist en .env)
    if not email_puede_buscar(usuario_email):
        abort(403)  # logueado pero sin permiso

@busquedas_bp.route("/")
def pagina_busquedas():
    _check_perm()
    return render_template("busquedas.html")

@busquedas_bp.route("/api/resultados", methods=["POST"])
def api_busquedas():
    _check_perm()

    usuario_id = session.get("usuario_id")
    if not usuario_id:
        abort(401)

    id_grupo = get_id_grupo_actual(usuario_id)
    if not id_grupo:
        abort(400)

    data = request.get_json(silent=True) or {}
    q = (data.get("q") or "").strip()
    f_desde = (data.get("desde") or "").strip()
    f_hasta = (data.get("hasta") or "").strip()

    sql = ["""
        SELECT R.id, R.fecha, U.nombre AS usuario, R.puntuacion
        FROM Resultados R
        JOIN Usuarios U ON U.id = R.id_usuario
        WHERE R.id_grupo = ?
    """]
    params = [id_grupo]

    if q:
        like = f"%{q}%"
        sql.append("AND (U.nombre LIKE ? OR U.email LIKE ?)")
        params += [like, like]
    if f_desde:
        sql.append("AND date(R.fecha) >= date(?)")
        params.append(f_desde)
    if f_hasta:
        sql.append("AND date(R.fecha) <= date(?)")
        params.append(f_hasta)

    sql.append("ORDER BY R.fecha DESC LIMIT 200")

    with db_lock, get_conn() as conn:
        cur = conn.cursor()
        cur.execute(" ".join(sql), params)
        rows = [dict(r) for r in cur.fetchall()]

    return jsonify({"ok": True, "data": rows})
