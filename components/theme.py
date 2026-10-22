"""Design tokens, global CSS and the Plotly layout shared by every chart.

Two themes: ``light`` (default, matches the stainless-steel product) and
``dark`` ("control room", for wall displays). Chart series colours come from a
colour-blind-validated categorical order; status colours are reserved for
state and always appear with an icon and a text label.
"""

from __future__ import annotations

import streamlit as st

TOKENS = {
    "light": {
        "bg": "#eef2f6", "surface": "#ffffff", "surface2": "#f5f7fa", "border": "#dbe2ea",
        "text": "#0b1f3a", "text2": "#47586f", "muted": "#7a889b",
        "accent": "#0e8fb0", "accent_soft": "#e3f4f9", "steel": "linear-gradient(180deg,#ffffff 0%,#eef2f6 100%)",
        "grid": "#e6eaf0", "axis": "#c3cad4",
        "pm25": "#2a78d6", "pm10": "#eb6834", "inlet": "#2a78d6", "outlet": "#1baf7a",
        "series3": "#6250d6", "ref": "#7a889b",
        "demo_bg": "#fff4d6", "demo_text": "#7a4b00", "demo_border": "#f2c45a",
    },
    "dark": {
        "bg": "#070f1c", "surface": "#0e1a2c", "surface2": "#12223a", "border": "#1e3150",
        "text": "#e8eef7", "text2": "#a8b6ca", "muted": "#7d8ea6",
        "accent": "#38c7e8", "accent_soft": "#0f2c40", "steel": "linear-gradient(180deg,#12223a 0%,#0e1a2c 100%)",
        "grid": "#1a2a42", "axis": "#2b3f5e",
        "pm25": "#3987e5", "pm10": "#d95926", "inlet": "#3987e5", "outlet": "#199e70",
        "series3": "#9085e9", "ref": "#8a9ab0",
        "demo_bg": "#3a2a05", "demo_text": "#ffd479", "demo_border": "#8a6512",
    },
}

STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b", "neutral": "#898781"}

# US EPA AQI category colours (part of the published method)
AQI_COLORS = {
    "Good": "#00a33a", "Moderate": "#e6b800", "Unhealthy for Sensitive Groups": "#ff7e00",
    "Unhealthy": "#e0002a", "Very Unhealthy": "#8f3f97", "Hazardous": "#7e0023",
}


def current_theme() -> str:
    """Follow the viewer's own light/dark choice (app menu → Settings), per browser.

    The palettes for both are defined in .streamlit/config.toml ([theme.light] /
    [theme.dark]); this picks the matching tokens for our custom HTML and charts.
    """
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # older Streamlit or no browser context (tests)
        return "light"


def tok() -> dict:
    return TOKENS[current_theme()]


def inject_css() -> None:
    t = tok()
    st.markdown(f"""
<style>
:root {{
  --ag-bg:{t['bg']}; --ag-surface:{t['surface']}; --ag-surface2:{t['surface2']}; --ag-border:{t['border']};
  --ag-text:{t['text']}; --ag-text2:{t['text2']}; --ag-muted:{t['muted']}; --ag-accent:{t['accent']};
  --ag-accent-soft:{t['accent_soft']}; --ag-steel:{t['steel']};
  --ag-good:{STATUS['good']}; --ag-warning:{STATUS['warning']}; --ag-serious:{STATUS['serious']};
  --ag-critical:{STATUS['critical']}; --ag-neutral:{STATUS['neutral']};
  --ag-demo-bg:{t['demo_bg']}; --ag-demo-text:{t['demo_text']}; --ag-demo-border:{t['demo_border']};
}}
html, body, [class*="css"] {{ font-family: "Segoe UI", system-ui, -apple-system, sans-serif; }}
.stApp {{ background: var(--ag-bg); color: var(--ag-text); }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1480px; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {{ border-radius: 8px; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {{ background: rgba(56,199,232,.18); }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span {{ color: #e6eef8 !important; }}
h1, h2, h3, h4 {{ color: var(--ag-text); letter-spacing: -.01em; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background: var(--ag-surface); border-color: var(--ag-border) !important; border-radius: 14px; }}

/* header */
.ag-header {{ display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
  background: var(--ag-steel); border:1px solid var(--ag-border); border-radius:16px; padding:14px 20px;
  box-shadow: 0 1px 2px rgba(11,31,58,.06); position:relative; overflow:hidden; }}
.ag-header::after {{ content:""; position:absolute; left:0; right:0; bottom:0; height:3px;
  background: linear-gradient(90deg, transparent, var(--ag-accent), transparent); opacity:.8; }}
.ag-brand {{ display:flex; align-items:center; gap:14px; }}
.ag-brand-name {{ font-size:1.65rem; font-weight:800; color:var(--ag-text); letter-spacing:-.02em; line-height:1; }}
.ag-brand-name span {{ color: var(--ag-accent); }}
.ag-brand-sub {{ font-size:.78rem; color:var(--ag-text2); letter-spacing:.14em; text-transform:uppercase; margin-top:4px; }}
.ag-chips {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
.ag-chip {{ display:inline-flex; align-items:center; gap:6px; padding:5px 11px; border-radius:999px;
  background: var(--ag-surface); border:1px solid var(--ag-border); font-size:.8rem; color:var(--ag-text2); white-space:nowrap; }}
.ag-chip b {{ color: var(--ag-text); font-weight:600; }}
.ag-demo {{ background: var(--ag-demo-bg); color: var(--ag-demo-text); border:1px solid var(--ag-demo-border);
  font-weight:700; letter-spacing:.06em; }}
.ag-demo-strip {{ margin:10px 0 4px; padding:7px 14px; border-radius:10px; background: var(--ag-demo-bg);
  border:1px solid var(--ag-demo-border); color: var(--ag-demo-text); font-size:.82rem; }}

/* cards */
.ag-card {{ background: var(--ag-surface); border:1px solid var(--ag-border); border-radius:14px; padding:16px 18px;
  height:100%; box-shadow: 0 1px 2px rgba(11,31,58,.05); }}
.ag-kpi-label {{ font-size:.78rem; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--ag-text2); }}
.ag-kpi-top {{ display:flex; justify-content:space-between; align-items:center; gap:8px; }}
.ag-kpi-value {{ font-size:2.35rem; font-weight:700; color:var(--ag-text); line-height:1.1; margin:8px 0 4px; }}
.ag-kpi-value .unit {{ font-size:.95rem; font-weight:500; color:var(--ag-muted); margin-left:6px; }}
.ag-kpi-value.na {{ font-size:1.25rem; color:var(--ag-muted); font-weight:600; margin:18px 0 10px; }}
.ag-kpi-foot {{ font-size:.8rem; color:var(--ag-text2); display:flex; align-items:center; gap:6px; flex-wrap:wrap; }}
.ag-kpi-sub {{ font-size:.76rem; color:var(--ag-muted); margin-top:6px; }}
.ag-tag {{ font-size:.66rem; font-weight:700; letter-spacing:.08em; padding:2px 7px; border-radius:6px;
  background: var(--ag-demo-bg); color: var(--ag-demo-text); border:1px solid var(--ag-demo-border); }}
.ag-tag.meas {{ background: var(--ag-accent-soft); color: var(--ag-accent); border-color: transparent; }}
.ag-aqi {{ display:flex; align-items:center; gap:16px; margin-top:8px; }}
.ag-aqi-ring {{ width:84px; height:84px; border-radius:50%; display:flex; align-items:center; justify-content:center;
  font-size:1.9rem; font-weight:800; color:var(--ag-text); border:7px solid; background: var(--ag-surface2); flex:none; }}
.ag-aqi-cat {{ font-weight:700; color: var(--ag-text); font-size:1.02rem; }}
.ag-bar {{ height:8px; background: var(--ag-surface2); border:1px solid var(--ag-border); border-radius:999px; overflow:hidden; margin-top:8px; }}
.ag-bar > div {{ height:100%; background: var(--ag-accent); border-radius:999px; transition: width .6s ease; }}

/* status */
.ag-status {{ display:inline-flex; align-items:center; gap:5px; font-weight:600; font-size:.8rem; }}
.ag-status svg {{ flex:none; }}
.ag-row {{ display:flex; justify-content:space-between; align-items:center; gap:10px; padding:8px 0;
  border-bottom:1px solid var(--ag-border); font-size:.86rem; color:var(--ag-text); }}
.ag-row:last-child {{ border-bottom:none; }}
.ag-row small {{ color: var(--ag-muted); display:block; font-size:.74rem; }}
.ag-section {{ font-size:1rem; font-weight:700; color:var(--ag-text); margin:0 0 2px; display:flex; align-items:center; gap:8px; }}
.ag-section-sub {{ font-size:.8rem; color:var(--ag-muted); margin-bottom:10px; }}
.ag-reason {{ background: var(--ag-accent-soft); border-left:3px solid var(--ag-accent); padding:9px 12px;
  border-radius:8px; font-size:.85rem; color:var(--ag-text); margin:10px 0; }}
.ag-big {{ font-size:2.6rem; font-weight:800; color:var(--ag-text); line-height:1; }}
.ag-big .unit {{ font-size:1rem; color:var(--ag-muted); font-weight:500; margin-left:4px; }}
.ag-mini {{ display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-top:12px; }}
.ag-mini > div {{ background: var(--ag-surface2); border:1px solid var(--ag-border); border-radius:10px; padding:8px 10px; }}
.ag-mini .k {{ font-size:.7rem; color:var(--ag-muted); text-transform:uppercase; letter-spacing:.07em; }}
.ag-mini .v {{ font-size:1.05rem; font-weight:700; color:var(--ag-text); }}
.ag-footer {{ display:grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap:10px; margin-top:16px; }}
.ag-footer > div {{ background: var(--ag-surface); border:1px solid var(--ag-border); border-radius:12px; padding:10px 14px; }}
.ag-footer .k {{ font-size:.7rem; color:var(--ag-muted); text-transform:uppercase; letter-spacing:.07em; }}
.ag-footer .v {{ font-size:1rem; font-weight:700; color:var(--ag-text); }}
.ag-note {{ font-size:.78rem; color:var(--ag-muted); }}
.ag-placeholder {{ border:2px dashed var(--ag-border); border-radius:14px; background: var(--ag-surface2);
  min-height:340px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px;
  color: var(--ag-muted); text-align:center; padding:24px; }}
.ag-formula {{ font-family: Consolas, "Cascadia Mono", monospace; background: var(--ag-surface2); border:1px solid var(--ag-border);
  border-radius:8px; padding:8px 12px; font-size:.84rem; color: var(--ag-text); }}
/* technical tower diagram */
.sx {{ display:block; max-width:620px; margin:0 auto; font-family:"Segoe UI", system-ui, sans-serif; }}
.sx-st0 {{ stop-color:{t['axis']}; }} .sx-st1 {{ stop-color:{t['surface']}; }} .sx-st2 {{ stop-color:{t['muted']}; }}
.sx-body {{ fill:url(#sxSteel); stroke:var(--ag-muted); stroke-width:1; }}
.sx-base {{ fill:var(--ag-text); opacity:.75; }}
.sx-neck {{ fill:var(--ag-muted); }}
.sx-dome {{ fill:#1c2b40; stroke:var(--ag-muted); }}
.sx-lens {{ fill:var(--ag-accent); }}
.sx-cut {{ fill:var(--ag-surface2); stroke:var(--ag-border); stroke-dasharray:4 3; }}
.sx-fan {{ fill:none; stroke:var(--ag-text2); stroke-width:1.5; }}
.sx-blade {{ fill:var(--ag-accent); opacity:.75; }}
.sx-pleat {{ fill:none; stroke:var(--ag-text2); stroke-width:1.1; }}
.sx-screen {{ fill:#0b1f3a; stroke:var(--ag-muted); }}
.sx-accentfill {{ fill:var(--ag-accent); }}
.sx-accent {{ fill:none; stroke:var(--ag-accent); stroke-width:2.5; }}
.sx-door {{ fill:none; stroke:var(--ag-text2); stroke-width:1.2; }}
.sx-pre {{ fill:var(--ag-surface2); stroke:var(--ag-text2); stroke-dasharray:2 2; }}
.sx-slot {{ fill:var(--ag-text); opacity:.55; }}
.sx-sensor {{ fill:var(--ag-accent); }}
.sx-flow {{ fill:none; stroke:var(--ag-accent); stroke-width:2.2; stroke-linecap:round; stroke-linejoin:round; }}
.sx-flowin {{ fill:none; stroke:var(--ag-accent); stroke-width:1.6; stroke-dasharray:5 5; opacity:.8; }}
.sx-call {{ fill:none; stroke:var(--ag-muted); stroke-width:1; }}
.sx-dot {{ fill:var(--ag-surface); stroke:var(--ag-accent); stroke-width:1.6; }}
.sx-title {{ fill:var(--ag-text); font-size:12.5px; font-weight:700; }}
.sx-value {{ fill:var(--ag-accent); font-size:12px; font-weight:600; }}
.sx-head {{ fill:var(--ag-muted); font-size:11px; letter-spacing:.08em; }}
.sx-watermark {{ opacity:.07; }}
.ag-watermark {{ position:fixed; right:2vw; bottom:3vh; width:34vw; max-width:520px; opacity:.05;
  pointer-events:none; z-index:0; text-align:center; }}
.ag-watermark svg {{ width:100%; height:auto; }}
.ag-watermark div {{ font-size:4.2vw; font-weight:800; color:var(--ag-text); letter-spacing:-.02em; margin-top:-2vw; }}
.ag-legend {{ display:flex; flex-wrap:wrap; gap:14px; font-size:.8rem; color:var(--ag-text2); margin-top:4px; }}
.ag-legend span {{ display:inline-flex; align-items:center; gap:6px; }}
.ag-legend i {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
.ag-aqi {{ flex-wrap: wrap; }}
.ag-aqi > div:last-child {{ flex: 1 1 110px; min-width: 0; }}
@media (max-width: 1300px) {{ .ag-aqi-ring {{ width:66px; height:66px; font-size:1.5rem; border-width:6px; }}
  .ag-kpi-value {{ font-size: 1.9rem; }} }}
@media (max-width: 1100px) {{ .ag-footer {{ grid-template-columns: repeat(2, minmax(0,1fr)); }} }}
</style>
""", unsafe_allow_html=True)


def plotly_layout(height: int = 320, **overrides) -> dict:
    t = tok()
    layout = dict(
        height=height,
        margin=dict(l=8, r=8, t=30, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family='"Segoe UI", system-ui, sans-serif', size=12, color=t["text2"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(color=t["text2"])),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=t["surface"], bordercolor=t["border"], font=dict(color=t["text"])),
        xaxis=dict(showgrid=False, linecolor=t["axis"], tickcolor=t["axis"], ticks="outside",
                   tickfont=dict(color=t["muted"]), title_font=dict(color=t["text2"])),
        yaxis=dict(gridcolor=t["grid"], zeroline=False, linecolor=t["axis"],
                   tickfont=dict(color=t["muted"]), title_font=dict(color=t["text2"])),
    )
    layout.update(overrides)
    return layout


PLOTLY_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}
