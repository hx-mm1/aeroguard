"""Technical cut-away diagram of the AeroGuard tower, annotated with live values.

Pure SVG (no images). Colours come from CSS classes defined in theme.py, so the
drawing follows the light/dark theme.
"""

from __future__ import annotations

import html

from components.ui import LOGO_PATHS

# (anchor x, anchor y, label y, title, value key) — left callouts end at x=176
_LEFT = [
    (266, 100, 96, "360° camera", "camera"),
    (224, 238, 226, "Smart status display", "display"),
    (215, 366, 344, "Coarse pre-filter", "prefilter"),
    (196, 412, 412, "360° intake · inlet sensors", "inlet"),
    (190, 462, 478, "Controller · 4G / Wi-Fi", "network"),
]
# right callouts start at x=386
_RIGHT = [
    (372, 62, 40, "Filtered-air outlet", "outlet"),
    (318, 158, 140, "EC fan stage", "fan"),
    (318, 250, 232, "HEPA-grade main filter", "filter"),
    (352, 300, 318, "Service door", "door"),
    (356, 412, 404, "Single-pass removal", "removal"),
]


def _callout(ax, ay, ly, title, value, side) -> str:
    if side == "left":
        ex, tx, anchor = 176, 170, "end"
    else:
        ex, tx, anchor = 386, 392, "start"
    return (f'<polyline class="sx-call" points="{ax},{ay} {ex + (8 if side == "left" else -8)},{ly} {ex},{ly}"/>'
            f'<circle class="sx-dot" cx="{ax}" cy="{ay}" r="3"/>'
            f'<text class="sx-title" x="{tx}" y="{ly - 3}" text-anchor="{anchor}">{html.escape(title)}</text>'
            f'<text class="sx-value" x="{tx}" y="{ly + 12}" text-anchor="{anchor}">{html.escape(value)}</text>')


def tower_schematic(values: dict, title: str = "") -> str:
    """Return an SVG string. ``values`` maps callout keys to short display strings."""
    v = {k: values.get(k, "—") for k in ("camera", "display", "prefilter", "inlet", "network",
                                         "outlet", "fan", "filter", "door", "removal")}
    slots = "".join(f'<rect class="sx-slot" x="206" y="{y}" width="148" height="4" rx="2"/>'
                    for y in range(380, 446, 9))
    pleats = "M248 206 " + " ".join(f"L{x} {316 if i % 2 else 206}" for i, x in enumerate(range(254, 340, 6), 1))
    out_arrows = "".join(f'<path class="sx-flow" d="M{x} 30 L{x} 6 M{x - 5} 12 L{x} 5 L{x + 5} 12"/>'
                         for x in (215, 248, 280, 312, 345))
    in_arrows = "".join(
        f'<path class="sx-flow" d="M150 {y} L190 {y} M184 {y - 5} L191 {y} L184 {y + 5}"/>'
        f'<path class="sx-flow" d="M410 {y} L370 {y} M376 {y - 5} L369 {y} L376 {y + 5}"/>'
        for y in (388, 412, 436))
    left = "".join(_callout(ax, ay, ly, t, v[k], "left") for ax, ay, ly, t, k in _LEFT)
    right = "".join(_callout(ax, ay, ly, t, v[k], "right") for ax, ay, ly, t, k in _RIGHT)
    head = f'<text class="sx-head" x="280" y="510" text-anchor="middle">{html.escape(title)}</text>' if title else ""
    return f"""<svg class="sx" viewBox="0 0 560 520" width="100%" role="img" aria-label="AeroGuard tower cut-away diagram">
<defs>
 <linearGradient id="sxSteel" x1="0" x2="1"><stop offset="0" class="sx-st0"/><stop offset=".45" class="sx-st1"/><stop offset="1" class="sx-st2"/></linearGradient>
</defs>
<g class="sx-watermark" transform="translate(150 120) scale(5.4)">{LOGO_PATHS}</g>
{out_arrows}
<ellipse class="sx-body" cx="280" cy="50" rx="112" ry="13"/>
<rect class="sx-body" x="168" y="50" width="224" height="20"/>
<ellipse class="sx-body" cx="280" cy="70" rx="112" ry="13"/>
<path class="sx-accent" d="M170 58 Q280 74 390 58"/>
<rect class="sx-body" x="222" y="80" width="116" height="52" rx="4"/>
<rect class="sx-neck" x="266" y="80" width="28" height="10"/>
<circle class="sx-dome" cx="280" cy="100" r="15"/><circle class="sx-lens" cx="280" cy="100" r="5.5"/>
<rect class="sx-body" x="214" y="132" width="132" height="54" rx="4"/>
<rect class="sx-cut" x="226" y="138" width="108" height="42" rx="3"/>
<circle class="sx-fan" cx="280" cy="159" r="17"/>
<path class="sx-blade" d="M280 159 L280 143 A16 16 0 0 1 294 151 Z M280 159 L294 167 A16 16 0 0 1 280 175 Z M280 159 L266 167 A16 16 0 0 1 266 151 Z"/>
<rect class="sx-body" x="204" y="186" width="152" height="176" rx="4"/>
<rect class="sx-cut" x="244" y="198" width="98" height="124" rx="3"/>
<path class="sx-pleat" d="{pleats}"/>
<rect class="sx-screen" x="212" y="204" width="26" height="72" rx="3"/>
<rect class="sx-accentfill" x="223" y="218" width="4" height="34" rx="2"/>
<rect class="sx-door" x="344" y="206" width="10" height="110" rx="2"/>
<rect class="sx-accentfill" x="346" y="252" width="3" height="14" rx="1"/>
<path class="sx-flowin" d="M330 352 L330 150"/>
<path class="sx-flow" d="M325 158 L330 148 L335 158"/>
<rect class="sx-pre" x="212" y="362" width="136" height="10" rx="2"/>
<rect class="sx-body" x="198" y="372" width="164" height="80" rx="4"/>
{slots}
<rect class="sx-sensor" x="186" y="402" width="12" height="20" rx="2"/>
<rect class="sx-base" x="186" y="452" width="188" height="16" rx="4"/>
<rect class="sx-base" x="174" y="468" width="212" height="12" rx="4"/>
{in_arrows}
{left}{right}{head}
</svg>"""
