#!/usr/bin/env python3
"""
integral_app.py

A Tkinter desktop application that lets users input definite integrals
(with implicit multiplication like '3x' or '2sin(x)'), automatically
generates a step‑by‑step Manim animation of the solution, and displays
the resulting video in the GUI.

Requirements:
    pip install manim sympy tkVideoPlayer
    # plus LaTeX (with amsmath, etc.) and FFmpeg on your PATH
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

import sympy
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)

from manim import Scene, MathTex, ReplacementTransform
from tkVideoPlayer import TkinterVideo

# Allow input like '3x' → '3*x'
_transformations = standard_transformations + (
    implicit_multiplication_application,
)


class IntegralApp:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title("Integral Solver with Manim")
        master.geometry("1000x700")

        # ——— Layout frames ———
        input_frame   = ttk.Frame(master)
        video_frame   = ttk.Frame(master)
        control_frame = ttk.Frame(master)

        input_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        video_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True,
                         padx=10, pady=10)
        control_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # ——— Input widgets ———
        ttk.Label(input_frame, text="Integrand:").grid(
            row=0, column=0, sticky="e")
        self.integrand_entry = ttk.Entry(input_frame, width=30)
        self.integrand_entry.grid(row=0, column=1, columnspan=3,
                                  padx=5, pady=5)

        ttk.Label(input_frame, text="Variable:").grid(
            row=1, column=0, sticky="e")
        self.var_choice = tk.StringVar(value="x")
        ttk.Combobox(input_frame, textvariable=self.var_choice,
                     values=["x", "y", "t"], width=3)\
            .grid(row=1, column=1, sticky="w", padx=5)

        ttk.Label(input_frame, text="Lower bound:").grid(
            row=1, column=2, sticky="e")
        self.lower_entry = ttk.Entry(input_frame, width=8)
        self.lower_entry.grid(row=1, column=3, sticky="w", padx=5)

        ttk.Label(input_frame, text="Upper bound:").grid(
            row=2, column=2, sticky="e")
        self.upper_entry = ttk.Entry(input_frame, width=8)
        self.upper_entry.grid(row=2, column=3, sticky="w", padx=5)

        # Symbol palette (decorative buttons — skip in Tab order)
        palette = ttk.Frame(input_frame)
        palette.grid(row=2, column=0, columnspan=2, pady=(5, 0))
        for sym, txt in [("π", "pi"), ("sin", "sin()"),
                         ("cos", "cos()"), ("^", "**")]:
            ttk.Button(palette, text=sym, width=4,
                       command=lambda s=txt: self.insert_symbol(s),
                       takefocus=0) \
                .pack(side=tk.LEFT, padx=2)

        # Solve button
        self.solve_btn = ttk.Button(
            input_frame, text="Solve & Animate",
            command=self.start_solve)
        self.solve_btn.grid(row=3, column=0, columnspan=4, pady=(10, 0))

        # ——— Video player ———
        self.videoplayer = TkinterVideo(video_frame, scaled=True)
        self.videoplayer.pack(fill=tk.BOTH, expand=True)

        # ——— Prev/Next controls ———
        self.prev_btn = ttk.Button(
            control_frame, text="<< Prev Step",
            command=self.prev_step, state=tk.DISABLED)
        self.next_btn = ttk.Button(
            control_frame, text="Next Step >>",
            command=self.next_step, state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT,  padx=20)
        self.next_btn.pack(side=tk.RIGHT, padx=20)

        # Initial focus so typing works immediately
        self.integrand_entry.focus_set()
        self.master.after(50, self.master.focus_force)  # grab focus

        # Step state
        self.step_times: list[float] = []
        self.current_step: int = 0

    # ——————————————————————————————————————————
    #  Helper / callback methods
    # ——————————————————————————————————————————
    def insert_symbol(self, sym: str) -> None:
        idx = self.integrand_entry.index(tk.INSERT)
        self.integrand_entry.insert(idx, sym)
        if sym.endswith("()"):
            self.integrand_entry.icursor(idx + len(sym) - 1)

    def start_solve(self) -> None:
        """Validate fields, disable controls, and spawn worker thread."""
        integrand = self.integrand_entry.get().strip()
        lower     = self.lower_entry.get().strip()
        upper     = self.upper_entry.get().strip()

        if not integrand or not lower or not upper:
            messagebox.showerror(
                "Error",
                "Please fill in the integrand and both bounds."
            )
            return

        # Disable while computing
        self.solve_btn.config(state=tk.DISABLED)
        self.prev_btn.config(state=tk.DISABLED)
        self.next_btn.config(state=tk.DISABLED)

        threading.Thread(
            target=self.solve_worker,
            args=(integrand, self.var_choice.get(), lower, upper),
            daemon=True
        ).start()

    def solve_worker(self, integrand_str: str, var: str,
                     a_str: str, b_str: str) -> None:
        """Heavy SymPy + Manim work off the main thread."""
        try:
            x  = sympy.symbols(var)
            ld = {"sin": sympy.sin, "cos": sympy.cos,
                  "pi": sympy.pi, var: x}

            expr  = parse_expr(integrand_str, ld,
                               transformations=_transformations)
            F     = sympy.integrate(expr, x)
            lower = parse_expr(a_str, ld,
                               transformations=_transformations)
            upper = parse_expr(b_str, ld,
                               transformations=_transformations)
            result = sympy.integrate(expr, (x, lower, upper))

            expr_tex  = rf"\int_{{{a_str}}}^{{{b_str}}}" \
                        rf" {sympy.latex(expr)}\,d{var}"
            anti_tex  = rf"\left[{sympy.latex(F)}\right]" \
                        rf"_{{{a_str}}}^{{{b_str}}}"
            Fu        = sympy.latex(F.subs(x, upper))
            Fl        = sympy.latex(F.subs(x, lower))
            eval_tex  = rf"{Fu} - {Fl}"
            final_tex = sympy.latex(sympy.simplify(result))

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
            video_path = scene.renderer.file_writer.movie_file_path

            self.master.after(0, lambda: self.finish_render(video_path))

        except Exception as e:
            self.master.after(
                0, lambda: messagebox.showerror("Error", str(e)))
            self.master.after(
                0, lambda: self.solve_btn.config(state=tk.NORMAL))

    def finish_render(self, video_path: str) -> None:
        self.videoplayer.load(video_path)
        self.videoplayer.play()

        dur = self.videoplayer.video_info().get("duration", 0)
        if dur <= 0:
            messagebox.showerror("Error", "Could not read video duration.")
            self.solve_btn.config(state=tk.NORMAL)
            return

        seg = dur / 3.0
        self.step_times = [0, seg, 2 * seg]
        self.current_step = 0

        self.solve_btn.config(state=tk.NORMAL)
        self.prev_btn.config(state=tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL)

    def prev_step(self) -> None:
        if self.current_step > 0:
            self.current_step -= 1
            self.videoplayer.seek(int(self.step_times[self.current_step]))
        self.prev_btn.config(
            state=tk.NORMAL if self.current_step > 0 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL)

    def next_step(self) -> None:
        if self.current_step < len(self.step_times) - 1:
            self.current_step += 1
            self.videoplayer.seek(int(self.step_times[self.current_step]))
        self.next_btn.config(
            state=tk.NORMAL if self.current_step < len(self.step_times) - 1
            else tk.DISABLED)
        self.prev_btn.config(state=tk.NORMAL)


if __name__ == "__main__":
    root = tk.Tk()
    IntegralApp(root)
    root.mainloop()
