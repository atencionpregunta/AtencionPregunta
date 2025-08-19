from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/admin", methods=["GET"])
def panel_admin():
    if not session.get("is_admin"):
        # SIN prefijo admin/ porque tus templates están todos en /templates
        return render_template("panel_login.html")
    return render_template("panel.html")

@admin_bp.route("/admin/login", methods=["GET", "POST"])
def login_admin():
    if request.method == "GET":
        if session.get("is_admin"):
            return redirect(url_for("admin.panel_admin"))
        return render_template("panel_login.html")

    # POST: validar contraseña
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
