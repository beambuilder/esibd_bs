"""
Syringe Pump GUI — simple tkinter control panel.

Launch:
    python syringe_pump_gui.py

Requires the esibd_bs package to be installed (pip install -e .)
so that `from devices.syringe_pump import SyringePump` works.
"""

import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# Add src to path so the import works when running from this folder
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from devices.syringe_pump.syringe_pump import SyringePump


class SyringePumpGUI(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Syringe Pump Control")
        self.resizable(False, False)
        self.configure(bg="#f0f0f0")

        self.pump: SyringePump | None = None
        self._build_ui()

    # ---- UI construction --------------------------------------------------
    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        # --- Connection frame ---
        conn = ttk.LabelFrame(self, text="Connection", padding=8)
        conn.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        ttk.Label(conn, text="Port").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar(value="COM7")
        ttk.Entry(conn, textvariable=self.port_var, width=10).grid(
            row=0, column=1, padx=(5, 15))

        ttk.Label(conn, text="Baud").grid(row=0, column=2, sticky="w")
        self.baud_var = tk.StringVar(value="38400")
        ttk.Entry(conn, textvariable=self.baud_var, width=8).grid(
            row=0, column=3, padx=(5, 15))

        self.btn_connect = ttk.Button(conn, text="Connect",
                                      command=self._on_connect)
        self.btn_connect.grid(row=0, column=4, padx=5)

        self.btn_disconnect = ttk.Button(conn, text="Disconnect",
                                         command=self._on_disconnect,
                                         state="disabled")
        self.btn_disconnect.grid(row=0, column=5, padx=5)

        self.lbl_status = ttk.Label(conn, text="Disconnected",
                                    foreground="red")
        self.lbl_status.grid(row=0, column=6, padx=(10, 0))

        # --- Parameters frame ---
        params = ttk.LabelFrame(self, text="Parameters", padding=8)
        params.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        def _param_row(parent, row, label, default, unit_text):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=str(default))
            ttk.Entry(parent, textvariable=var, width=10).grid(
                row=row, column=1, padx=5)
            ttk.Label(parent, text=unit_text, foreground="#666").grid(
                row=row, column=2, sticky="w")
            return var

        self.vol_var = _param_row(params, 0, "Volume", "1.0", "mL")
        self.dia_var = _param_row(params, 1, "Diameter", "4.64", "mm")
        self.rate_var = _param_row(params, 2, "Pump rate", "120.0", "mL/hr")
        self.wdraw_var = _param_row(params, 3, "Withdraw rate", "120.0", "mL/hr")

        ttk.Label(params, text="Units").grid(row=4, column=0, sticky="w")
        self.units_var = tk.StringVar(value="mL/hr")
        units_cb = ttk.Combobox(params, textvariable=self.units_var, width=8,
                                values=["mL/min", "mL/hr", "\u03bcL/min", "\u03bcL/hr"],
                                state="readonly")
        units_cb.grid(row=4, column=1, padx=5)

        self.btn_apply = ttk.Button(params, text="Apply to pump",
                                    command=self._on_apply, state="disabled")
        self.btn_apply.grid(row=5, column=0, columnspan=3, pady=(8, 0))

        # --- Control frame ---
        ctrl = ttk.LabelFrame(self, text="Control", padding=8)
        ctrl.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="ew")

        self.btn_start = ttk.Button(ctrl, text="Start",
                                    command=self._on_start, state="disabled")
        self.btn_start.grid(row=0, column=0, padx=5)

        self.btn_pause = ttk.Button(ctrl, text="Pause",
                                    command=self._on_pause, state="disabled")
        self.btn_pause.grid(row=0, column=1, padx=5)

        self.btn_stop = ttk.Button(ctrl, text="Stop",
                                   command=self._on_stop, state="disabled")
        self.btn_stop.grid(row=0, column=2, padx=5)

        self.btn_withdraw = ttk.Button(ctrl, text="Withdraw",
                                       command=self._on_withdraw,
                                       state="disabled")
        self.btn_withdraw.grid(row=0, column=3, padx=5)

        self.lbl_pump_status = ttk.Label(ctrl, text="")
        self.lbl_pump_status.grid(row=0, column=4, padx=(15, 0))

    # ---- helpers ----------------------------------------------------------
    def _set_connected_state(self, connected: bool):
        state = "normal" if connected else "disabled"
        self.btn_disconnect.config(state=state)
        self.btn_apply.config(state=state)
        self.btn_start.config(state=state)
        self.btn_pause.config(state=state)
        self.btn_stop.config(state=state)
        self.btn_withdraw.config(state=state)
        self.btn_connect.config(state="disabled" if connected else "normal")
        if connected:
            self.lbl_status.config(text="Connected", foreground="green")
        else:
            self.lbl_status.config(text="Disconnected", foreground="red")

    def _read_params(self):
        """Push GUI parameter values into the pump object."""
        self.pump.volume = float(self.vol_var.get())
        self.pump.diameter = float(self.dia_var.get())
        self.pump.pump_rate = float(self.rate_var.get())
        self.pump.withdraw_rate = float(self.wdraw_var.get())
        self.pump.units = self.units_var.get()

    # ---- callbacks --------------------------------------------------------
    def _on_connect(self):
        try:
            port = self.port_var.get().strip()
            baud = int(self.baud_var.get().strip())
            self.pump = SyringePump("gui_pump", port=port, baudrate=baud)
            if self.pump.connect():
                self._set_connected_state(True)
            else:
                messagebox.showerror("Connection failed",
                                     f"Could not open {port}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_disconnect(self):
        if self.pump:
            self.pump.disconnect()
        self._set_connected_state(False)

    def _on_apply(self):
        try:
            self._read_params()
            self.pump.apply_parameters()
            self.lbl_pump_status.config(text="Parameters applied",
                                        foreground="blue")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_start(self):
        try:
            self._read_params()
            self.pump.apply_parameters()
            self.pump.start_pump()
            self.lbl_pump_status.config(text="Pumping...", foreground="green")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_pause(self):
        try:
            if self.pump:
                self.pump.pause_pump()
            self.lbl_pump_status.config(text="Paused", foreground="orange")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_stop(self):
        try:
            if self.pump:
                self.pump.stop_pump()
            self.lbl_pump_status.config(text="Stopped", foreground="red")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_withdraw(self):
        """Run withdraw in a background thread so the GUI stays responsive."""
        try:
            self._read_params()
            self.btn_withdraw.config(state="disabled")
            self.btn_start.config(state="disabled")
            self.lbl_pump_status.config(text="Withdrawing...",
                                        foreground="orange")

            def _do():
                try:
                    self.pump.withdraw()
                    self.after(0, lambda: self.lbl_pump_status.config(
                        text="Withdraw done", foreground="green"))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Error", str(e)))
                finally:
                    self.after(0, lambda: self.btn_withdraw.config(
                        state="normal"))
                    self.after(0, lambda: self.btn_start.config(
                        state="normal"))

            threading.Thread(target=_do, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def destroy(self):
        if self.pump and self.pump.is_connected:
            self.pump.stop_pump()
            self.pump.disconnect()
        super().destroy()


if __name__ == "__main__":
    app = SyringePumpGUI()
    app.mainloop()
