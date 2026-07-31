"""Live browser plot of the DT-670 readout served by firmware/dt670srv.

Polls the Arduino's JSON endpoint (http://192.168.2.2/) at 2 Hz and streams
diode voltage and temperature into two linked HoloViews/Bokeh plots served
by Panel on http://localhost:5006.

Run (Anaconda prompt):
    conda activate base
    python python\\liveplot.py
"""

import datetime as dt

import holoviews as hv
import pandas as pd
import panel as pn
import requests
from holoviews.streams import Buffer

hv.extension("bokeh")

URL = "http://192.168.2.2/"
PERIOD_MS = 500          # 2 Hz
HISTORY = 3600           # samples kept in the plot (30 min at 2 Hz)
PORT = 5006

VOLT_COLOR = "#3B6FB6"
TEMP_COLOR = "#C55A2B"


def _empty_frame():
    return pd.DataFrame(
        {
            "time": pd.Series(dtype="datetime64[ns]"),
            "v": pd.Series(dtype=float),
            "t_k": pd.Series(dtype=float),
        }
    )


def make_app():
    buf = Buffer(_empty_frame(), length=HISTORY, index=False)
    status = pn.pane.Markdown("**Status:** waiting for first sample …")

    def poll():
        try:
            reply = requests.get(URL, timeout=0.4)
            data = reply.json()
        except Exception as exc:
            status.object = (
                f"**Status:** no response from {URL} "
                f"({exc.__class__.__name__})"
            )
            return

        t_k = data.get("t_k")
        volts = data.get("v")
        flag = data.get("flag", "?")
        buf.send(
            pd.DataFrame(
                {
                    "time": [dt.datetime.now()],
                    "v": [volts],
                    "t_k": [float("nan") if t_k is None else t_k],
                }
            )
        )
        temp_txt = "—" if t_k is None else f"{t_k:.2f} K ({t_k - 273.15:.2f} °C)"
        status.object = (
            f"**V_diode:** {volts:.5f} V &nbsp;&nbsp; "
            f"**T:** {temp_txt} &nbsp;&nbsp; **flag:** `{flag}`"
        )

    common = dict(
        responsive=True,
        height=300,
        line_width=2,
        framewise=True,
        show_grid=True,
        gridstyle={"grid_line_alpha": 0.25},
        tools=["hover"],
        xlabel="time",
    )
    curve_v = hv.DynamicMap(
        lambda data: hv.Curve(data, "time", "v", label="V_diode").opts(
            color=VOLT_COLOR, ylabel="V_diode [V]", **common
        ),
        streams=[buf],
    )
    curve_t = hv.DynamicMap(
        lambda data: hv.Curve(data, "time", "t_k", label="T").opts(
            color=TEMP_COLOR, ylabel="T [K]", **common
        ),
        streams=[buf],
    )

    pn.state.add_periodic_callback(poll, period=PERIOD_MS)

    return pn.Column(
        pn.pane.Markdown("## DT-670 live readout — 192.168.2.2, 2 Hz"),
        status,
        pn.pane.HoloViews(curve_v, sizing_mode="stretch_width"),
        pn.pane.HoloViews(curve_t, sizing_mode="stretch_width"),
        sizing_mode="stretch_width",
    )


if __name__ == "__main__":
    pn.serve(make_app, port=PORT, show=True, title="DT-670 live")
