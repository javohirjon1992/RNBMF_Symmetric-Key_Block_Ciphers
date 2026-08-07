"""Tkinter desktop UI for the RNBMF Dynamic S-Box Laboratory."""
from __future__ import annotations

import csv
import json
import queue
import random
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np

from core import (
    AES_POLYNOMIAL,
    CSV_COLUMNS,
    DEFAULT_A1_SEED,
    DEFAULT_A2_SEED,
    DEFAULT_POLYNOMIAL,
    EXTENDED_COLUMNS,
    GenerationConfig,
    algebraic_degrees,
    analyze_sbox,
    boomerang_uniformity,
    bits_to_matrix,
    generate_candidate,
    is_irreducible_degree8,
    load_clean_csv,
    matrix_is_nonsingular,
    parse_sbox,
    row_for_csv,
    validate_config,
    validate_rnbmf_seed,
    write_csv,
)


APP_TITLE = "RNBMF Dynamic S-Box Laboratory"

DISPLAY_COLUMNS = [
    "A1_Matrix_Rotation_Offset",
    "A2_Matrix_Rotation_Offset",
    "b1_Binary_Constant",
    "b2_Binary_Constant",
    "Nonlinearity_Min",
    "Nonlinearity_Max",
    "Linear_Probability",
    "SAC_Min",
    "SAC_Max",
    "SAC_Average",
    "SAC_Square_Deviation",
    "Differential_Uniformity_Max",
    "Cycle_Count",
    "Cycle_Lengths",
    "Boomerang_Uniformity",
    "Generation_Time",
]

COLUMN_TITLES = {
    "A1_Matrix_Rotation_Offset": "A1 Offset",
    "A2_Matrix_Rotation_Offset": "A2 Offset",
    "b1_Binary_Constant": "b1",
    "b2_Binary_Constant": "b2",
    "Nonlinearity_Min": "NL Min",
    "Nonlinearity_Max": "NL Max",
    "Linear_Probability": "LP",
    "SAC_Min": "SAC Min",
    "SAC_Max": "SAC Max",
    "SAC_Average": "SAC Avg",
    "SAC_Square_Deviation": "SAC Dev.",
    "Differential_Uniformity_Max": "DU",
    "Cycle_Count": "Cycles",
    "Cycle_Lengths": "Cycle Lengths",
    "Boomerang_Uniformity": "BU",
    "Generation_Time": "Time",
}


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)


class RNBMFApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1480x900")
        self.minsize(1180, 720)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._configure_style()
        self.results: list[dict] = []
        self.filtered_indices: list[int] = []
        self.worker_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.event_queue: queue.Queue = queue.Queue()
        self.session_csv_path: Path | None = None
        self.session_csv_handle = None
        self.session_csv_writer = None
        self.start_time = None
        self.matched_count = 0
        self.generated_count = 0
        self.skipped_count = 0
        self._current_result_index: int | None = None

        self._build_menu()
        self._build_header()
        self._build_tabs()
        self._set_status("Ready")
        self.after(80, self._poll_events)

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        bg = "#f3f6fa"
        panel = "#ffffff"
        accent = "#1769aa"
        self.configure(bg=bg)
        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("Header.TFrame", background="#102a43")
        style.configure("Header.TLabel", background="#102a43", foreground="white", font=("Segoe UI", 18, "bold"))
        style.configure("SubHeader.TLabel", background="#102a43", foreground="#d9e7f5", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 12, "bold"), background=panel, foreground="#243b53")
        style.configure("CardValue.TLabel", font=("Segoe UI", 17, "bold"), background=panel, foreground="#102a43")
        style.configure("CardName.TLabel", font=("Segoe UI", 9), background=panel, foreground="#627d98")
        style.configure("TLabel", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 6))
        style.configure("Accent.TButton", background=accent, foreground="white", font=("Segoe UI", 9, "bold"), padding=(12, 7))
        style.map("Accent.TButton", background=[("active", "#0f548c"), ("disabled", "#9fb3c8")])
        style.configure("Danger.TButton", background="#c0392b", foreground="white")
        style.map("Danger.TButton", background=[("active", "#9f2f24")])
        style.configure("TLabelframe", background=panel, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=panel, foreground="#334e68", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=27, font=("Consolas", 9), background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#d9e2ec", foreground="#243b53")
        style.map("Treeview", background=[("selected", "#d5e8f7")], foreground=[("selected", "#102a43")])
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=(16, 8))

    def _build_menu(self):
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Import CSV...", command=self.import_csv)
        file_menu.add_command(label="Export Compatible CSV...", command=lambda: self.export_csv(False))
        file_menu.add_command(label="Export Extended CSV...", command=lambda: self.export_csv(True))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menu.add_cascade(label="File", menu=file_menu)

        tools = tk.Menu(menu, tearoff=0)
        tools.add_command(label="Validate RNBMF Seeds", command=self.validate_seeds)
        tools.add_command(label="Analyze Selected S-Box", command=self.compute_advanced_for_selected)
        menu.add_cascade(label="Tools", menu=tools)

        help_menu = tk.Menu(menu, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menu)

    def _build_header(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(20, 12))
        header.pack(fill="x")
        left = ttk.Frame(header, style="Header.TFrame")
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text=APP_TITLE, style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="Dynamic 8×8 S-box generation, cryptographic evaluation, cycle analysis, BCT, and CSV export",
            style="SubHeader.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        right = ttk.Frame(header, style="Header.TFrame")
        right.pack(side="right")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(right, textvariable=self.status_var, style="SubHeader.TLabel").pack(anchor="e")

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.generator_tab = ttk.Frame(self.notebook)
        self.results_tab = ttk.Frame(self.notebook)
        self.inspector_tab = ttk.Frame(self.notebook)
        self.data_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.generator_tab, text="Generator")
        self.notebook.add(self.results_tab, text="Results")
        self.notebook.add(self.inspector_tab, text="Inspector")
        self.notebook.add(self.data_tab, text="CSV & Data")
        self._build_generator_tab()
        self._build_results_tab()
        self._build_inspector_tab()
        self._build_data_tab()

    def _build_generator_tab(self):
        container = ttk.Frame(self.generator_tab)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)

        left_scroll = ScrollableFrame(container)
        left_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        right_scroll = ScrollableFrame(container)
        right_scroll.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        left = left_scroll.inner
        right = right_scroll.inner

        seeds = ttk.LabelFrame(left, text="RNBMF Matrix Seeds", padding=12)
        seeds.pack(fill="x", padx=8, pady=8)
        self.a1_seed_var = tk.StringVar(value=DEFAULT_A1_SEED)
        self.a2_seed_var = tk.StringVar(value=DEFAULT_A2_SEED)
        ttk.Label(seeds, text="A1 64-bit seed").grid(row=0, column=0, sticky="w")
        ttk.Entry(seeds, textvariable=self.a1_seed_var, font=("Consolas", 9)).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        ttk.Label(seeds, text="A2 64-bit seed").grid(row=2, column=0, sticky="w")
        ttk.Entry(seeds, textvariable=self.a2_seed_var, font=("Consolas", 9)).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        ttk.Button(seeds, text="Validate Seeds", command=self.validate_seeds).grid(row=4, column=0, sticky="w")
        ttk.Button(seeds, text="Restore Defaults", command=self.restore_defaults).grid(row=4, column=1, sticky="w", padx=6)
        self.seed_status_var = tk.StringVar(value="Not validated")
        ttk.Label(seeds, textvariable=self.seed_status_var).grid(row=5, column=0, columnspan=3, sticky="w", pady=(7, 0))
        seeds.columnconfigure(0, weight=1)

        generation = ttk.LabelFrame(left, text="Generation Parameters", padding=12)
        generation.pack(fill="x", padx=8, pady=8)
        self.iterations_var = tk.IntVar(value=100)
        self.offset_mode_var = tk.StringVar(value="Random")
        self.k1_var = tk.IntVar(value=0)
        self.k2_var = tk.IntVar(value=0)
        self.b1_mode_var = tk.StringVar(value="Random")
        self.b2_mode_var = tk.StringVar(value="Random")
        self.b1_var = tk.StringVar(value="00000000")
        self.b2_var = tk.StringVar(value="00000000")
        self.polynomial_var = tk.StringVar(value=DEFAULT_POLYNOMIAL)
        self.random_seed_var = tk.StringVar(value="")
        self.advanced_var = tk.BooleanVar(value=False)
        self.require_nonsingular_var = tk.BooleanVar(value=True)

        labels = [
            ("Iterations", 0), ("Offset mode", 1), ("Fixed A1 offset", 2), ("Fixed A2 offset", 3),
            ("b1 mode", 4), ("Fixed b1", 5), ("b2 mode", 6), ("Fixed b2", 7),
            ("GF(2^8) polynomial", 8), ("Random seed (optional)", 9),
        ]
        for text, row in labels:
            ttk.Label(generation, text=text).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Spinbox(generation, from_=1, to=1000000, textvariable=self.iterations_var, width=14).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Combobox(generation, textvariable=self.offset_mode_var, values=["Random", "Fixed", "Sequential"], state="readonly").grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Spinbox(generation, from_=0, to=63, textvariable=self.k1_var).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Spinbox(generation, from_=0, to=63, textvariable=self.k2_var).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Combobox(generation, textvariable=self.b1_mode_var, values=["Random", "Fixed"], state="readonly").grid(row=4, column=1, sticky="ew", pady=3)
        ttk.Entry(generation, textvariable=self.b1_var, font=("Consolas", 9)).grid(row=5, column=1, sticky="ew", pady=3)
        ttk.Combobox(generation, textvariable=self.b2_mode_var, values=["Random", "Fixed"], state="readonly").grid(row=6, column=1, sticky="ew", pady=3)
        ttk.Entry(generation, textvariable=self.b2_var, font=("Consolas", 9)).grid(row=7, column=1, sticky="ew", pady=3)
        poly_combo = ttk.Combobox(generation, textvariable=self.polynomial_var, values=[DEFAULT_POLYNOMIAL, AES_POLYNOMIAL])
        poly_combo.grid(row=8, column=1, sticky="ew", pady=3)
        ttk.Entry(generation, textvariable=self.random_seed_var).grid(row=9, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(generation, text="Compute algebraic degree and boomerang uniformity during generation", variable=self.advanced_var).grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Checkbutton(generation, text="Require selected A1/A2 matrices to be nonsingular over GF(2)", variable=self.require_nonsingular_var).grid(row=11, column=0, columnspan=2, sticky="w", pady=2)
        generation.columnconfigure(1, weight=1)

        filters = ttk.LabelFrame(right, text="Optional Candidate Filters", padding=12)
        filters.pack(fill="x", padx=8, pady=8)
        self.only_matching_var = tk.BooleanVar(value=False)
        self.min_nl_var = tk.DoubleVar(value=0.0)
        self.max_du_var = tk.IntVar(value=256)
        self.sac_min_lower_var = tk.DoubleVar(value=0.0)
        self.sac_max_upper_var = tk.DoubleVar(value=1.0)
        self.max_sac_dev_var = tk.DoubleVar(value=1.0)
        self.min_cycle_var = tk.IntVar(value=1)
        self.require_bijective_var = tk.BooleanVar(value=True)
        filter_defs = [
            ("Minimum nonlinearity", self.min_nl_var),
            ("Maximum differential uniformity", self.max_du_var),
            ("SAC minimum lower bound", self.sac_min_lower_var),
            ("SAC maximum upper bound", self.sac_max_upper_var),
            ("Maximum SAC deviation", self.max_sac_dev_var),
            ("Minimum cycle length", self.min_cycle_var),
        ]
        for r, (name, var) in enumerate(filter_defs):
            ttk.Label(filters, text=name).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(filters, textvariable=var, width=18).grid(row=r, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(filters, text="Require a bijective S-box", variable=self.require_bijective_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Checkbutton(filters, text="Store only candidates that satisfy all filters", variable=self.only_matching_var).grid(row=7, column=0, columnspan=2, sticky="w", pady=2)
        filters.columnconfigure(1, weight=1)

        controls = ttk.LabelFrame(right, text="Run Control", padding=12)
        controls.pack(fill="x", padx=8, pady=8)
        button_row = ttk.Frame(controls, style="Panel.TFrame")
        button_row.pack(fill="x")
        self.start_btn = ttk.Button(button_row, text="Start Generation", style="Accent.TButton", command=self.start_generation)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(button_row, text="Stop", style="Danger.TButton", command=self.stop_generation, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(button_row, text="Clear Results", command=self.clear_results).pack(side="left", padx=6)
        self.progress = ttk.Progressbar(controls, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(12, 4))
        self.progress_text_var = tk.StringVar(value="0 / 0")
        ttk.Label(controls, textvariable=self.progress_text_var).pack(anchor="w")

        cards = ttk.Frame(right, style="Panel.TFrame")
        cards.pack(fill="x", padx=8, pady=8)
        self.card_vars = {}
        for i, name in enumerate(["Generated", "Stored", "Matched", "Skipped", "Rate / s", "Elapsed"]):
            card = ttk.Frame(cards, style="Panel.TFrame", padding=10)
            card.grid(row=i // 3, column=i % 3, sticky="nsew", padx=3, pady=3)
            var = tk.StringVar(value="0")
            self.card_vars[name] = var
            ttk.Label(card, text=name, style="CardName.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=var, style="CardValue.TLabel").pack(anchor="w")
        for col in range(3):
            cards.columnconfigure(col, weight=1)

        notes = ttk.LabelFrame(right, text="CSV Compatibility", padding=12)
        notes.pack(fill="x", padx=8, pady=8)
        ttk.Label(
            notes,
            text=(
                "Compatible export preserves the 25-column schema of the supplied dataset. "
                "Extended export additionally includes algebraic degree, boomerang uniformity, "
                "bijectivity, and minimum cycle length."
            ),
            wraplength=570,
            justify="left",
        ).pack(anchor="w")

    def _build_results_tab(self):
        toolbar = ttk.Frame(self.results_tab, padding=(6, 6))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Import CSV", command=self.import_csv).pack(side="left")
        ttk.Button(toolbar, text="Export Compatible CSV", command=lambda: self.export_csv(False)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Export Extended CSV", command=lambda: self.export_csv(True)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Inspect Selected", command=self.inspect_selected).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Compute Advanced Metrics", command=self.compute_advanced_for_selected).pack(side="left", padx=4)
        ttk.Label(toolbar, text="View:").pack(side="left", padx=(14, 4))
        self.view_mode_var = tk.StringVar(value="Compact")
        view_combo = ttk.Combobox(toolbar, textvariable=self.view_mode_var, values=["Compact", "Full CSV", "Extended"], state="readonly", width=12)
        view_combo.pack(side="left")
        view_combo.bind("<<ComboboxSelected>>", lambda e: self._update_result_view_mode())
        ttk.Label(toolbar, text="Search:").pack(side="left", padx=(14, 4))
        self.search_var = tk.StringVar(value="")
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=30)
        search.pack(side="left")
        search.bind("<KeyRelease>", lambda e: self.refresh_results_tree())

        table_frame = ttk.Frame(self.results_tab)
        table_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.results_tree = ttk.Treeview(table_frame, columns=EXTENDED_COLUMNS, displaycolumns=DISPLAY_COLUMNS, show="headings", selectmode="browse")
        ybar = ttk.Scrollbar(table_frame, orient="vertical", command=self.results_tree.yview)
        xbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.results_tree.xview)
        self.results_tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        for col in EXTENDED_COLUMNS:
            self.results_tree.heading(col, text=COLUMN_TITLES.get(col, col))
            width = 125
            if col == "Calculated_S_Box":
                width = 420
            elif col in ("A1_Binary_Matrix", "A2_Binary_Matrix"):
                width = 430
            elif col in ("Cycle_Lengths", "Fixed_Points_Hex", "Opposite_Fixed_Points_Hex"):
                width = 220
            elif col in ("b1_Binary_Constant", "b2_Binary_Constant"):
                width = 95
            self.results_tree.column(col, width=width, minwidth=70, anchor="center")
        self.results_tree.bind("<Double-1>", lambda e: self.inspect_selected())
        self.results_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def _build_inspector_tab(self):
        top = ttk.Frame(self.inspector_tab, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Compute Advanced Metrics", command=self.compute_advanced_for_selected).pack(side="left")
        ttk.Button(top, text="Copy S-Box as Decimal List", command=lambda: self.copy_sbox(False)).pack(side="left", padx=4)
        ttk.Button(top, text="Copy S-Box as Hex Table", command=lambda: self.copy_sbox(True)).pack(side="left", padx=4)
        self.inspector_title_var = tk.StringVar(value="No result selected")
        ttk.Label(top, textvariable=self.inspector_title_var, font=("Segoe UI", 11, "bold")).pack(side="right")

        pane = ttk.Panedwindow(self.inspector_tab, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left, weight=3)
        pane.add(right, weight=2)

        metrics = ttk.LabelFrame(left, text="Cryptographic Metrics", padding=10)
        metrics.pack(fill="x", pady=(0, 6))
        self.metric_vars = {}
        metric_names = [
            "Nonlinearity_Min", "Nonlinearity_Max", "Linear_Probability", "LAT_Max",
            "SAC_Min", "SAC_Max", "SAC_Average", "SAC_Square_Deviation",
            "Differential_Uniformity_Max", "Cycle_Count", "Minimum_Cycle_Length",
            "Algebraic_Degree_Min", "Algebraic_Degree_Max", "Boomerang_Uniformity",
        ]
        for i, name in enumerate(metric_names):
            box = ttk.Frame(metrics, style="Panel.TFrame", padding=5)
            box.grid(row=i // 4, column=i % 4, sticky="nsew", padx=3, pady=3)
            ttk.Label(box, text=name.replace("_", " "), style="CardName.TLabel").pack(anchor="w")
            var = tk.StringVar(value="—")
            self.metric_vars[name] = var
            ttk.Label(box, textvariable=var, font=("Segoe UI", 11, "bold"), background="#ffffff").pack(anchor="w")
        for c in range(4):
            metrics.columnconfigure(c, weight=1)

        sbox_frame = ttk.LabelFrame(left, text="S-Box Lookup Table (Hexadecimal)", padding=8)
        sbox_frame.pack(fill="both", expand=True)
        self.sbox_tree = ttk.Treeview(sbox_frame, columns=[f"c{i:X}" for i in range(16)], show="tree headings", height=16)
        self.sbox_tree.heading("#0", text="")
        self.sbox_tree.column("#0", width=38, minwidth=38, anchor="center")
        for i in range(16):
            col = f"c{i:X}"
            self.sbox_tree.heading(col, text=f"{i:X}")
            self.sbox_tree.column(col, width=42, minwidth=38, anchor="center")
        self.sbox_tree.pack(fill="both", expand=True)

        matrices = ttk.LabelFrame(right, text="Affine Matrices and Parameters", padding=8)
        matrices.pack(fill="x")
        matrix_container = ttk.Frame(matrices, style="Panel.TFrame")
        matrix_container.pack(fill="x")
        self.a1_matrix_text = tk.Text(matrix_container, height=9, width=19, font=("Consolas", 10), wrap="none")
        self.a2_matrix_text = tk.Text(matrix_container, height=9, width=19, font=("Consolas", 10), wrap="none")
        self.a1_matrix_text.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.a2_matrix_text.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.parameter_text = tk.Text(matrices, height=7, font=("Consolas", 9), wrap="word")
        self.parameter_text.pack(fill="x", pady=(6, 0))

        sac_frame = ttk.LabelFrame(right, text="Strict Avalanche Criterion Matrix", padding=8)
        sac_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.sac_tree = ttk.Treeview(sac_frame, columns=[f"o{i}" for i in range(8)], show="tree headings", height=8)
        self.sac_tree.heading("#0", text="In/Out")
        self.sac_tree.column("#0", width=58, minwidth=58, anchor="center")
        for i in range(8):
            col = f"o{i}"
            self.sac_tree.heading(col, text=f"b{i}")
            self.sac_tree.column(col, width=62, minwidth=55, anchor="center")
        self.sac_tree.pack(fill="both", expand=True)
        self.cycle_var = tk.StringVar(value="Cycle lengths: —")
        ttk.Label(right, textvariable=self.cycle_var, wraplength=470, justify="left").pack(fill="x", pady=6)

    def _build_data_tab(self):
        top = ttk.Frame(self.data_tab, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Dataset / CSV Tools", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            top,
            text="The compatible export follows the exact 25-column header used by the supplied RNBMF dataset.",
        ).pack(anchor="w", pady=(2, 8))
        buttons = ttk.Frame(top)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Import CSV", command=self.import_csv).pack(side="left")
        ttk.Button(buttons, text="Export Compatible CSV", command=lambda: self.export_csv(False)).pack(side="left", padx=5)
        ttk.Button(buttons, text="Export Extended CSV", command=lambda: self.export_csv(True)).pack(side="left", padx=5)
        ttk.Button(buttons, text="Open Session Output Folder", command=self.open_output_folder).pack(side="left", padx=5)

        columns_frame = ttk.LabelFrame(self.data_tab, text="Compatible CSV Columns", padding=10)
        columns_frame.pack(fill="x", padx=10, pady=8)
        self.schema_text = tk.Text(columns_frame, height=9, font=("Consolas", 9), wrap="word")
        self.schema_text.pack(fill="x")
        self.schema_text.insert("1.0", ", ".join(CSV_COLUMNS))
        self.schema_text.configure(state="disabled")

        log_frame = ttk.LabelFrame(self.data_tab, text="Application Log", padding=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = tk.Text(log_frame, font=("Consolas", 9), wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self._log("Application initialized.")

    def _config_from_ui(self) -> GenerationConfig:
        seed_text = self.random_seed_var.get().strip()
        random_seed = int(seed_text) if seed_text else None
        return GenerationConfig(
            a1_seed=self.a1_seed_var.get().strip(),
            a2_seed=self.a2_seed_var.get().strip(),
            polynomial=self.polynomial_var.get().strip(),
            iterations=int(self.iterations_var.get()),
            offset_mode=self.offset_mode_var.get(),
            fixed_k1=int(self.k1_var.get()),
            fixed_k2=int(self.k2_var.get()),
            b1_mode=self.b1_mode_var.get(),
            b2_mode=self.b2_mode_var.get(),
            fixed_b1=self.b1_var.get().strip(),
            fixed_b2=self.b2_var.get().strip(),
            random_seed=random_seed,
            compute_advanced=bool(self.advanced_var.get()),
            only_matching=bool(self.only_matching_var.get()),
            min_nonlinearity=float(self.min_nl_var.get()),
            max_du=int(self.max_du_var.get()),
            sac_min_lower=float(self.sac_min_lower_var.get()),
            sac_max_upper=float(self.sac_max_upper_var.get()),
            max_sac_deviation=float(self.max_sac_dev_var.get()),
            min_cycle_length=int(self.min_cycle_var.get()),
            require_bijective=bool(self.require_bijective_var.get()),
            require_nonsingular_matrices=bool(self.require_nonsingular_var.get()),
        )

    def start_generation(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        try:
            config = self._config_from_ui()
            validate_config(config)
        except Exception as exc:
            messagebox.showerror("Invalid Configuration", str(exc), parent=self)
            return

        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.configure(value=0)
        self.progress_text_var.set(f"0 / {config.iterations}")
        self.start_time = time.time()
        self.matched_count = 0
        self.generated_count = 0
        self.skipped_count = 0
        self._prepare_session_csv()
        self._set_status("Generating S-boxes...")
        self._log(f"Generation started: {config.iterations} candidates, offset mode={config.offset_mode}, polynomial={config.polynomial}.")
        self.worker_thread = threading.Thread(target=self._generation_worker, args=(config,), daemon=True)
        self.worker_thread.start()

    def _prepare_session_csv(self):
        outputs = Path(__file__).resolve().parent / "outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.session_csv_path = outputs / f"rnbmf_session_{stamp}.csv"
        self.session_csv_handle = self.session_csv_path.open("w", newline="", encoding="utf-8")
        self.session_csv_writer = csv.DictWriter(self.session_csv_handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        self.session_csv_writer.writeheader()
        self.session_csv_handle.flush()

    def _generation_worker(self, config: GenerationConfig):
        rng = random.Random(config.random_seed)
        stored = 0
        try:
            for i in range(config.iterations):
                if self.stop_event.is_set():
                    break
                try:
                    row, matched = generate_candidate(config, rng, i)
                except Exception as exc:
                    self.event_queue.put(("error", f"Candidate {i + 1}: {exc}"))
                    continue
                self.event_queue.put(("candidate", row, matched, i + 1, config.iterations))
                if row and (matched or not config.only_matching):
                    stored += 1
            self.event_queue.put(("finished", stored, self.stop_event.is_set()))
        except Exception as exc:
            self.event_queue.put(("fatal", str(exc)))

    def stop_generation(self):
        self.stop_event.set()
        self.stop_btn.configure(state="disabled")
        self._set_status("Stopping...")

    def _poll_events(self):
        try:
            while True:
                event = self.event_queue.get_nowait()
                kind = event[0]
                if kind == "candidate":
                    _, row, matched, current, total = event
                    self.generated_count = current
                    if not row:
                        self.skipped_count += 1
                    else:
                        if matched:
                            self.matched_count += 1
                        config_only = bool(self.only_matching_var.get())
                        if matched or not config_only:
                            self.results.append(row)
                            if self.session_csv_writer:
                                self.session_csv_writer.writerow(row_for_csv(row, extended=False))
                                if len(self.results) % 25 == 0:
                                    self.session_csv_handle.flush()
                            self._insert_result_tree_row(len(self.results) - 1, row)
                    self._update_progress(current, total)
                elif kind == "error":
                    self._log(event[1])
                elif kind == "finished":
                    _, stored, was_stopped = event
                    self._finish_generation(stored, was_stopped)
                elif kind == "fatal":
                    self._log("Generation failed: " + event[1])
                    messagebox.showerror("Generation Error", event[1], parent=self)
                    self._finish_generation(len(self.results), True)
        except queue.Empty:
            pass
        self.after(80, self._poll_events)

    def _update_progress(self, current: int, total: int):
        percent = (100.0 * current / total) if total else 0
        self.progress.configure(value=percent)
        self.progress_text_var.set(f"{current:,} / {total:,} ({percent:.1f}%)")
        elapsed = max(time.time() - self.start_time, 1e-9) if self.start_time else 0
        rate = current / elapsed if elapsed else 0
        self.card_vars["Generated"].set(f"{current:,}")
        self.card_vars["Stored"].set(f"{len(self.results):,}")
        self.card_vars["Matched"].set(f"{self.matched_count:,}")
        self.card_vars["Skipped"].set(f"{self.skipped_count:,}")
        self.card_vars["Rate / s"].set(f"{rate:.1f}")
        self.card_vars["Elapsed"].set(self._format_seconds(elapsed))

    def _finish_generation(self, stored: int, was_stopped: bool):
        if self.session_csv_handle:
            try:
                self.session_csv_handle.flush()
                self.session_csv_handle.close()
            except Exception:
                pass
            self.session_csv_handle = None
            self.session_csv_writer = None
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        state = "Stopped" if was_stopped else "Completed"
        self._set_status(f"{state}. Stored results: {stored:,}")
        if self.session_csv_path:
            self._log(f"{state}. Session-compatible CSV: {self.session_csv_path}")
        self.refresh_results_tree()

    def validate_seeds(self):
        try:
            a1 = validate_rnbmf_seed(self.a1_seed_var.get())
            a2 = validate_rnbmf_seed(self.a2_seed_var.get())
            polynomial = self.polynomial_var.get().strip()
            poly_ok = is_irreducible_degree8(polynomial)
            msg = (
                f"A1: {a1['nonsingular_count']}/64 nonsingular; "
                f"A2: {a2['nonsingular_count']}/64 nonsingular; "
                f"Polynomial irreducible: {'Yes' if poly_ok else 'No'}"
            )
            self.seed_status_var.set(msg)
            self._log(msg)
            if not a1["valid"]:
                self._log(f"A1 singular offsets: {a1['bad_offsets']}")
            if not a2["valid"]:
                self._log(f"A2 singular offsets: {a2['bad_offsets']}")
        except Exception as exc:
            messagebox.showerror("Seed Validation", str(exc), parent=self)

    def restore_defaults(self):
        self.a1_seed_var.set(DEFAULT_A1_SEED)
        self.a2_seed_var.set(DEFAULT_A2_SEED)
        self.polynomial_var.set(DEFAULT_POLYNOMIAL)
        self.seed_status_var.set("Not validated")

    def clear_results(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Generation Running", "Stop generation before clearing results.", parent=self)
            return
        self.results.clear()
        self.filtered_indices.clear()
        self._current_result_index = None
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self._clear_inspector()
        self.card_vars["Stored"].set("0")
        self._log("Results cleared.")

    def _display_value(self, row: dict, column: str):
        value = row.get(column, "")
        if column in {"Nonlinearity_Min", "Nonlinearity_Max", "LAT_Max"}:
            try:
                return f"{float(value):.4f}".rstrip("0").rstrip(".")
            except Exception:
                return value
        if column in {"Linear_Probability", "SAC_Min", "SAC_Max", "SAC_Average", "SAC_Square_Deviation"}:
            try:
                return f"{float(value):.6f}"
            except Exception:
                return value
        return str(value)

    def _insert_result_tree_row(self, index: int, row: dict):
        search = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        if search and search not in " ".join(str(row.get(c, "")) for c in DISPLAY_COLUMNS).lower():
            return
        values = [self._display_value(row, c) for c in EXTENDED_COLUMNS]
        self.results_tree.insert("", "end", iid=f"r{index}", values=values)

    def refresh_results_tree(self):
        if not hasattr(self, "results_tree"):
            return
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        search = self.search_var.get().strip().lower()
        for idx, row in enumerate(self.results):
            if search:
                hay = " ".join(str(row.get(c, "")) for c in EXTENDED_COLUMNS).lower()
                if search not in hay:
                    continue
            self._insert_result_tree_row(idx, row)

    def _update_result_view_mode(self):
        mode = self.view_mode_var.get() if hasattr(self, "view_mode_var") else "Compact"
        if mode == "Full CSV":
            self.results_tree.configure(displaycolumns=CSV_COLUMNS)
        elif mode == "Extended":
            self.results_tree.configure(displaycolumns=EXTENDED_COLUMNS)
        else:
            self.results_tree.configure(displaycolumns=DISPLAY_COLUMNS)

    def _on_tree_select(self, event=None):
        selection = self.results_tree.selection()
        if selection:
            try:
                self._current_result_index = int(selection[0][1:])
            except Exception:
                self._current_result_index = None

    def inspect_selected(self):
        selection = self.results_tree.selection()
        if selection:
            try:
                idx = int(selection[0][1:])
            except Exception:
                return
            self._current_result_index = idx
        if self._current_result_index is None or self._current_result_index >= len(self.results):
            messagebox.showinfo("Inspector", "Select a result first.", parent=self)
            return
        self._populate_inspector(self._current_result_index)
        self.notebook.select(self.inspector_tab)

    def _populate_inspector(self, index: int):
        row = self.results[index]
        sbox = parse_sbox(row["Calculated_S_Box"])
        # Recompute SAC if it was loaded from CSV or not retained.
        try:
            metrics = analyze_sbox(sbox, compute_advanced=False)
        except Exception as exc:
            messagebox.showerror("Inspector", str(exc), parent=self)
            return
        for key in self.metric_vars:
            value = row.get(key, metrics.get(key, ""))
            if value in (None, ""):
                value = "—"
            elif isinstance(value, float):
                value = f"{value:.6f}"
            self.metric_vars[key].set(str(value))

        self.inspector_title_var.set(f"Result #{index + 1}")
        for item in self.sbox_tree.get_children():
            self.sbox_tree.delete(item)
        for r in range(16):
            values = [f"{sbox[r * 16 + c]:02X}" for c in range(16)]
            self.sbox_tree.insert("", "end", text=f"{r:X}", values=values)

        self._set_text_widget(self.a1_matrix_text, self._matrix_block(row.get("A1_Binary_Matrix", ""), "A1"))
        self._set_text_widget(self.a2_matrix_text, self._matrix_block(row.get("A2_Binary_Matrix", ""), "A2"))
        params = (
            f"A1 rotation offset : {row.get('A1_Matrix_Rotation_Offset', '')}\n"
            f"A2 rotation offset : {row.get('A2_Matrix_Rotation_Offset', '')}\n"
            f"b1 constant        : {row.get('b1_Binary_Constant', '')}\n"
            f"b2 constant        : {row.get('b2_Binary_Constant', '')}\n"
            f"GF polynomial      : {row.get('GF_2_8_Irreducible_Polynomial', '')}\n"
            f"Generated          : {row.get('Generation_Date', '')} {row.get('Generation_Time', '')}"
        )
        self._set_text_widget(self.parameter_text, params)

        for item in self.sac_tree.get_children():
            self.sac_tree.delete(item)
        sac = metrics["SAC_Matrix"]
        for r in range(8):
            self.sac_tree.insert("", "end", text=f"b{r}", values=[f"{sac[r, c]:.4f}" for c in range(8)])
        cycle_value = row.get("Cycle_Lengths", json.dumps(metrics["Cycle_Lengths"]))
        self.cycle_var.set(f"Cycle lengths: {cycle_value}")

    def _matrix_block(self, bits, title):
        bits = str(bits).strip()
        try:
            m = bits_to_matrix(bits)
            lines = [f"{title} matrix"] + [" ".join(str(int(v)) for v in row) for row in m]
            return "\n".join(lines)
        except Exception:
            return f"{title} matrix\nUnavailable"

    @staticmethod
    def _set_text_widget(widget: tk.Text, text: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _clear_inspector(self):
        self.inspector_title_var.set("No result selected")
        for var in self.metric_vars.values():
            var.set("—")
        for tree in (self.sbox_tree, self.sac_tree):
            for item in tree.get_children():
                tree.delete(item)
        self._set_text_widget(self.a1_matrix_text, "")
        self._set_text_widget(self.a2_matrix_text, "")
        self._set_text_widget(self.parameter_text, "")
        self.cycle_var.set("Cycle lengths: —")

    def compute_advanced_for_selected(self):
        if self._current_result_index is None:
            selection = self.results_tree.selection() if hasattr(self, "results_tree") else ()
            if selection:
                self._current_result_index = int(selection[0][1:])
        if self._current_result_index is None or self._current_result_index >= len(self.results):
            messagebox.showinfo("Advanced Metrics", "Select a result first.", parent=self)
            return
        idx = self._current_result_index
        row = self.results[idx]
        try:
            self._set_status("Computing algebraic degree and BCT...")
            self.update_idletasks()
            sbox = parse_sbox(row["Calculated_S_Box"])
            deg_min, deg_max, _ = algebraic_degrees(sbox)
            bu = boomerang_uniformity(sbox)
            row["Algebraic_Degree_Min"] = deg_min
            row["Algebraic_Degree_Max"] = deg_max
            row["Boomerang_Uniformity"] = bu
            if hasattr(self, "metric_vars"):
                self.metric_vars["Algebraic_Degree_Min"].set(str(deg_min))
                self.metric_vars["Algebraic_Degree_Max"].set(str(deg_max))
                self.metric_vars["Boomerang_Uniformity"].set(str(bu))
            self.refresh_results_tree()
            self._log(f"Advanced metrics for result #{idx + 1}: degree={deg_min}..{deg_max}, BU={bu}.")
            self._set_status("Advanced metrics computed")
        except Exception as exc:
            messagebox.showerror("Advanced Metrics", str(exc), parent=self)
            self._set_status("Ready")

    def copy_sbox(self, hex_table: bool):
        if self._current_result_index is None or self._current_result_index >= len(self.results):
            messagebox.showinfo("Copy S-Box", "Select a result first.", parent=self)
            return
        sbox = parse_sbox(self.results[self._current_result_index]["Calculated_S_Box"])
        if hex_table:
            lines = [" ".join(f"{sbox[r*16+c]:02X}" for c in range(16)) for r in range(16)]
            text = "\n".join(lines)
        else:
            text = json.dumps(sbox)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status("S-box copied to clipboard")

    def import_csv(self):
        path = filedialog.askopenfilename(parent=self, title="Import RNBMF CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            rows = load_clean_csv(path)
            # Normalize imported rows enough for inspection and table display.
            added = 0
            for row in rows:
                if not row.get("Calculated_S_Box"):
                    continue
                try:
                    parse_sbox(row["Calculated_S_Box"])
                except Exception:
                    continue
                self.results.append(row)
                added += 1
            self.refresh_results_tree()
            self.card_vars["Stored"].set(f"{len(self.results):,}")
            self._log(f"Imported {added:,} valid rows from {path}.")
            self.notebook.select(self.results_tab)
            if added == 0:
                messagebox.showwarning(
                    "CSV Import",
                    "No valid rows were imported. The original supplied dataset contains malformed quoting in some rows; "
                    "new CSV files exported by this application use standards-compliant quoting.",
                    parent=self,
                )
        except Exception as exc:
            messagebox.showerror("CSV Import", str(exc), parent=self)

    def export_csv(self, extended: bool):
        if not self.results:
            messagebox.showinfo("Export CSV", "There are no results to export.", parent=self)
            return
        default = "rnbmf_results_extended.csv" if extended else "rnbmf_results.csv"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export CSV",
            defaultextension=".csv",
            initialfile=default,
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            write_csv(path, self.results, extended=extended)
            self._log(f"Exported {len(self.results):,} rows to {path}.")
            self._set_status("CSV exported")
        except Exception as exc:
            messagebox.showerror("Export CSV", str(exc), parent=self)

    def open_output_folder(self):
        folder = Path(__file__).resolve().parent / "outputs"
        folder.mkdir(exist_ok=True)
        import os, sys, subprocess
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showinfo("Output Folder", f"Session files are stored in:\n{folder}\n\n{exc}", parent=self)

    def show_about(self):
        messagebox.showinfo(
            "About",
            APP_TITLE + "\n\n"
            "A desktop interface for seed-induced dynamic 8×8 S-box generation.\n\n"
            "Standard analysis: vectorial nonlinearity, LP/LAT, SAC, differential uniformity, "
            "fixed/opposite fixed points, and permutation cycle structure.\n"
            "Advanced analysis: component algebraic degree and boomerang uniformity (BCT).\n\n"
            "The compatible CSV export preserves the supplied dataset schema.",
            parent=self,
        )

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _log(self, text: str):
        if not hasattr(self, "log_text"):
            return
        stamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{stamp}] {text}\n")
        self.log_text.see("end")

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _on_close(self):
        self.stop_event.set()
        if self.session_csv_handle:
            try:
                self.session_csv_handle.flush()
                self.session_csv_handle.close()
            except Exception:
                pass
        self.destroy()
