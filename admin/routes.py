from flask import render_template, request, redirect, url_for, session, flash
from . import admin_bp

@admin_bp.route("/admin")
def panel_admin():
    return render_template("admin/panel.html")

@admin_bp.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("admin_password", "")
    if password == "TU_CONTRASEÑA_SEGURA":
        session["is_admin"] = True
        flash("Has accedido al modo administrador.", "success")
        return redirect(url_for("admin.panel_admin"))
    flash("Contraseña incorrecta.", "error")
    return redirect(url_for("index"))
