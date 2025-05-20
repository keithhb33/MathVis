#!/usr/bin/env python3
"""
Integral Solver Web App (Flask + Manim)

All *.mp4 (partials + final) end up directly in  static/videos/
No media/, 1080p60/, or other quality sub‑folders survive the cleanup.
"""

from pathlib import Path
from uuid import uuid4
import threading
import shutil
from typing import Dict

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)

import sympy
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

from manim import Scene, MathTex, ReplacementTransform, config as mconfig

# ------------------------------------------------------------------------- #
APP = Flask(__name__)
APP.secret_key = "change‑me"

ROOT_DIR  = Path(__file__).parent.resolve()
VIDEO_DIR = ROOT_DIR / "static" / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

_transformations = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

TASKS: Dict[str, str] = {}      # vid → "pending" | "ready" | "error:<msg>"

# ------------------------------------------------------------------------- #
def _flatten_to_video_dir(src_dir: Path) -> None:
    """
    Move every *.mp4 found under *src_dir* (recursively) into VIDEO_DIR.
    Skip files that are *already* in VIDEO_DIR. Remove empty directories.
    """
    if not src_dir.exists():
        return

    for mp4 in src_dir.rglob("*.mp4"):
        if mp4.parent == VIDEO_DIR:    # already at destination
            continue
        dest = VIDEO_DIR / mp4.name
        if dest.exists():
            dest.unlink()
        shutil.move(mp4, dest)

    # prune empty directories depth‑first
    for p in sorted(src_dir.rglob("*"), reverse=True):
        try:
            p.rmdir()
        except OSError:
            pass

# ------------------------------------------------------------------------- #
def generate_integral_video(integrand: str,
                            var: str,
                            lower_s: str,
                            upper_s: str,
                            outfile: Path,
                            vid: str) -> None:
    TASKS[vid] = "pending"
    try:
        # 1) Force Manim to use static/videos
        mconfig.media_dir = str(VIDEO_DIR)
        mconfig.video_dir = str(VIDEO_DIR)          # Manim ≥ 0.20

        # 2) SymPy – build integral
        x  = sympy.symbols(var)
        ld = {"sin": sympy.sin, "cos": sympy.cos, "pi": sympy.pi, var: x}

        expr   = parse_expr(integrand, ld, transformations=_transformations)
        F      = sympy.integrate(expr, x)
        lower  = parse_expr(lower_s, ld, transformations=_transformations)
        upper  = parse_expr(upper_s, ld, transformations=_transformations)
        result = sympy.integrate(expr, (x, lower, upper))

        expr_tex  = rf"\int_{{{lower_s}}}^{{{upper_s}}} {sympy.latex(expr)}\,d{var}"
        anti_tex  = rf"\left[{sympy.latex(F)}\right]_{{{lower_s}}}^{{{upper_s}}}"
        eval_tex  = rf"{sympy.latex(F.subs(x, upper))} - {sympy.latex(F.subs(x, lower))}"
        final_tex = sympy.latex(sympy.simplify(result))

        # 3) Manim scene
        class IntegralScene(Scene):
            def construct(self_inner):
                eq1 = MathTex(expr_tex)
                eq2 = MathTex(anti_tex)
                eq3 = MathTex(rf"{eval_tex} = {final_tex}")
                self_inner.play(eq1.animate.scale(1))
                self_inner.wait(1)
                self_inner.play(ReplacementTransform(eq1, eq2))
                self_inner.wait(1)
                self_inner.play(ReplacementTransform(eq2, eq3))
                self_inner.wait(2)

        scene = IntegralScene()
        scene.render()

        # 4) Move final movie to UUID filename
        shutil.move(Path(scene.renderer.file_writer.movie_file_path), outfile)

        # 5) Flatten partial movie files
        partial_root = VIDEO_DIR / "partial_movie_files"
        _flatten_to_video_dir(partial_root)

        # 6) Flatten any quality sub‑folders created by Manim (1080p60, …)
        for sub in VIDEO_DIR.iterdir():
            if sub.is_dir() and sub.name != "partial_movie_files":
                _flatten_to_video_dir(sub)

        TASKS[vid] = "ready"

    except Exception as exc:
        APP.logger.exception("video render failed")
        outfile.unlink(missing_ok=True)
        TASKS[vid] = f"error:{exc}"

# ------------------------------------------------------------------------- #
@APP.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip()
                for k in ("integrand", "variable", "lower", "upper")}
        if not all(form.values()):
            flash("Please fill in the integrand and all bounds.", "danger")
            return redirect(url_for("index"))

        vid        = f"{uuid4().hex}.mp4"
        video_path = VIDEO_DIR / vid

        threading.Thread(
            target=generate_integral_video,
            args=(form["integrand"], form["variable"],
                  form["lower"], form["upper"], video_path, vid),
            daemon=False
        ).start()

        return redirect(url_for("result", vid=vid))

    return render_template("index.html")

# ------------------------------------------------------------------------- #
@APP.route("/result/<vid>")
def result(vid: str):
    video_path = VIDEO_DIR / vid
    return render_template(
        "result.html",
        vid=vid,
        video_url=url_for("static", filename=f"videos/{vid}"),
        ready=video_path.exists(),
    )

# ------------------------------------------------------------------------- #
@APP.route("/status/<vid>")
def status(vid: str):
    state = TASKS.get(vid, "pending")
    return jsonify({
        "ready": state == "ready",
        "error": state if state.startswith("error:") else None,
    })

# ------------------------------------------------------------------------- #
@APP.route("/latex", methods=["POST"])
def latex_preview():
    data      = request.get_json(silent=True) or {}
    integrand = data.get("integrand", "").strip()
    variable  = data.get("variable", "x").strip() or "x"
    lower     = data.get("lower", "").strip()
    upper     = data.get("upper", "").strip()

    try:
        x  = sympy.symbols(variable)
        ld = {"sin": sympy.sin, "cos": sympy.cos, "pi": sympy.pi, variable: x}

        expr_tex = sympy.latex(
            parse_expr(integrand, ld, transformations=_transformations)
        ) if integrand else ""

        lower_tex = sympy.latex(
            parse_expr(lower, ld, transformations=_transformations)
        ) if lower else ""

        upper_tex = sympy.latex(
            parse_expr(upper, ld, transformations=_transformations)
        ) if upper else ""

        return jsonify({"expr": expr_tex, "lower": lower_tex, "upper": upper_tex})

    except Exception:
        return jsonify({"expr": "", "lower": "", "upper": ""})

# ------------------------------------------------------------------------- #
if __name__ == "__main__":
    APP.run(debug=True, use_reloader=False)
