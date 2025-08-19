import os
from flask import render_template, request, redirect, url_for, session, flash
from . import admin_bp
from functools import wraps

# Contraseña de admin (desde .env o por defecto "admin123")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Decorador para proteger rutas admin
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("No tienes acceso. Inicia sesión como administrador.", "error")
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return wrapper

# Login administrador
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Sesión de administrador iniciada ✅", "success")
            return redirect(url_for("admin.panel"))
        flash("Contraseña incorrecta ❌", "error")
    return render_template("admin/login.html")

# Panel principal
@admin_bp.route("/")
@admin_required
def panel():
    return render_template("admin/panel.html")

# Logout
@admin_bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    flash("Sesión de administrador cerrada 👋", "info")
    return redirect(url_for("index"))
