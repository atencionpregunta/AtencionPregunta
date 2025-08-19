from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app

# Blueprint sin prefix (como pediste)
admin_bp = Blueprint("admin", __name__)

# Panel/admin landing
@admin_bp.route("/admin")
def panel_admin():
    # Si no está logueado como admin, muestra el formulario de acceso
    if not session.get("is_admin"):
        return render_template("admin/login_admin.html")
    # Si ya es admin, muestra el panel real
    return render_template("admin/panel.html")

# Login admin (valida contraseña)
@admin_bp.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("admin_password", "")
    if password == current_app.config.get("ADMIN_PASSWORD"):
        session["is_admin"] = True
        flash("Has accedido al modo administrador.", "success")
        return redirect(url_for("admin.panel_admin"))
    flash("Contraseña incorrecta.", "error")
    return redirect(url_for("admin.panel_admin"))

# Logout admin
@admin_bp.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    flash("Has salido del modo administrador.", "info")
    return redirect(url_for("index"))
