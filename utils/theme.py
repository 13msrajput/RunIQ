"""RunIQ look & feel: a Cricbuzz-inspired layout with dark (default) and light themes.

What lives here
* the colour palettes and one CSS block injected into every page
* the green top navigation bar (logo, page links, "More" menu, theme switch)
* HTML helpers: match cards, section titles, stat cards, profile headers, tables, charts

This is an ORIGINAL implementation inspired by the general layout and colour scheme of
cricket score sites. It uses RunIQ's own logo and none of Cricbuzz's logos, text or images.
"""

from __future__ import annotations

import html  # escape every dynamic value before putting it into HTML

import pandas as pd  # DataFrame -> HTML table
import plotly.express as px  # default colour sequence for every chart
import streamlit as st  # UI

from utils.branding import APP_NAME, logo_data_uri  # embedded logo
from utils.icons import icon  # inline SVG icons

# ----------------------------------------------------------------- palettes
DARK = {
    "bg": "#1e2729",
    "card": "#181a1b",
    "card2": "#232627",
    "bar": "#383c3f",
    "text": "#e8eaeb",
    "muted": "#9aa3a8",
    "border": "#33393c",
    "green": "#00755a",
    "green2": "#005a45",
    "accent": "#1fd3a2",
    "link": "#4d9fec",
    "live": "#ff5252",
    "warn-bg": "#3d1d00",
    "warn-text": "#ff9d3d",
    "shadow": "none",
}
LIGHT = {
    "bg": "#e3e6e8",
    "card": "#ffffff",
    "card2": "#f1f3f4",
    "bar": "#d5dadd",
    "text": "#1c1c1c",
    "muted": "#5f6b73",
    "border": "#d3d8db",
    "green": "#009270",
    "green2": "#00755a",
    "accent": "#00755a",
    "link": "#0b63c5",
    "live": "#d32f2f",
    "warn-bg": "#fff2e0",
    "warn-text": "#a24a00",
    "shadow": "0 1px 3px rgba(0,0,0,.12)",
}
FORMAT_COLORS = {
    "Test": "#c62828",
    "ODI": "#0b5fa5",
    "T20I": "#6b7378",
}  # chip colours per format
CHART_COLORS = [
    "#00a77f",
    "#4d9fec",
    "#ba0950",
    "#73229b",
    "#f5a623",
    "#046196",
    "#8bc34a",
    "#ff7043",
]  # plotly colour cycle

px.defaults.color_discrete_sequence = (
    CHART_COLORS  # RunIQ colours for every Plotly Express chart
)

PAGES = [  # (script path, label, Material icon) shown in the top bar
    ("main.py", "Home", ":material/home:"),
    ("pages/1_Matches.py", "Matches", ":material/sensors:"),
    ("pages/3_Series.py", "Series", ":material/calendar_month:"),
    ("pages/4_Teams.py", "Teams", ":material/groups:"),
    ("pages/5_Players.py", "Players", ":material/person:"),
    ("pages/6_Rankings.py", "Rankings", ":material/emoji_events:"),
    ("pages/7_Stats_and_Records.py", "Stats", ":material/query_stats:"),
    ("pages/8_News.py", "News", ":material/newspaper:"),
]
MORE_PAGES = [
    ("pages/2_Match_Centre.py", "Match Centre", ":material/scoreboard:"),
    ("pages/9_SQL_Analytics.py", "SQL Analytics", ":material/database:"),
    ("pages/10_Insights.py", "Insights", ":material/insights:"),
    ("pages/11_Manage_Data.py", "Manage Data", ":material/edit_note:"),
    ("pages/12_Data_and_Settings.py", "Data & Settings", ":material/settings:"),
]

_STATIC_CSS = """
.stApp{background:var(--bg);color:var(--text);font-family:"Inter","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;}
header,header[data-testid="stHeader"],.stAppHeader,[data-testid="stToolbar"],#MainMenu,footer,[data-testid="stDecoration"],
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{display:none!important;}
.block-container{max-width:1200px;padding:0 1rem 2rem 1rem;}
.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp li,.stApp label,
.stApp [data-testid="stMarkdownContainer"],.stApp [data-testid="stWidgetLabel"] *{color:var(--text);}
.stApp [data-testid="stCaptionContainer"],.stApp [data-testid="stCaptionContainer"] *{color:var(--muted);}
.stApp a{color:var(--link);}
.stApp hr{border-color:var(--border);}

/* ---- top bar ---- */
.st-key-topbar{background:var(--green);margin:0 -1rem 14px -1rem;padding:8px 18px;border-radius:0 0 8px 8px;box-shadow:var(--shadow);}
.st-key-topbar [data-testid="stHorizontalBlock"]{align-items:center;gap:.15rem;flex-wrap:nowrap!important;overflow-x:auto;}
.st-key-topbar [data-testid="stColumn"]{min-width:0!important;flex:1 1 auto!important;width:auto!important;}
.st-key-topbar *{color:#fff!important;}
.st-key-topbar [data-testid="stPageLink-NavLink"]{padding:8px 9px;border-radius:6px;justify-content:center;white-space:nowrap;}
.st-key-topbar [data-testid="stPageLink-NavLink"]:hover{background:rgba(255,255,255,.18);}
.st-key-topbar [data-testid="stPageLink-NavLink"][aria-current="page"]{background:rgba(0,0,0,.30);font-weight:700;}
.st-key-topbar [data-testid="stPageLink-NavLink"] p{font-size:.92rem;}
.st-key-topbar button{background:rgba(255,255,255,.14)!important;border:0!important;border-radius:6px!important;}
.st-key-topbar button:hover{background:rgba(255,255,255,.26)!important;}
.rq-brand{display:flex;align-items:center;gap:10px;white-space:nowrap;}
.rq-brand img{height:44px;width:44px;border-radius:11px;box-shadow:0 1px 4px rgba(0,0,0,.35);}
.rq-brand span{font-weight:800;font-size:1.25rem;letter-spacing:.3px;color:#fff;}
div[data-testid="stPopoverBody"],div[data-testid="stPopoverBody"] *{color:var(--text)!important;}
div[data-testid="stPopoverBody"]{background:var(--card)!important;border:1px solid var(--border);}
div[data-testid="stPopoverBody"] [data-testid="stPageLink-NavLink"]:hover{background:var(--card2);}

.st-key-quick{background:var(--card);border-radius:8px;padding:10px 12px;margin:6px 0 14px 0;border:1px solid var(--border);}
.st-key-quick [data-testid="stPageLink-NavLink"]{background:var(--card2);border:1px solid var(--border);border-radius:8px;padding:9px 12px;justify-content:center;}
.st-key-quick [data-testid="stPageLink-NavLink"]:hover{border-color:var(--accent);}
.st-key-quick [data-testid="stPageLink-NavLink"] *{color:var(--text)!important;}

.st-key-cta [data-testid="stPageLink-NavLink"]{background:var(--green);border-radius:8px;padding:12px 18px;justify-content:center;max-width:560px;}
.st-key-cta [data-testid="stPageLink-NavLink"]:hover{filter:brightness(1.12);}
.st-key-cta [data-testid="stPageLink-NavLink"] *{color:#fff!important;font-weight:700;}

/* ---- headings, panels ---- */
.cb-section{display:flex;align-items:center;gap:8px;color:var(--accent);font-weight:800;font-size:1.05rem;letter-spacing:.5px;text-transform:uppercase;margin:22px 0 10px 0;}
.cb-section svg{stroke:var(--accent);}
.cb-title{font-size:1.75rem;font-weight:800;margin:4px 0 2px 0;color:var(--text);display:flex;align-items:center;gap:10px;}
.cb-title svg{stroke:var(--accent);}
.cb-sub{color:var(--muted);font-size:.93rem;margin-bottom:12px;}
.cb-panel{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:12px;color:var(--text);box-shadow:var(--shadow);}
.cb-caution{background:var(--warn-bg);color:var(--warn-text);border-radius:8px;padding:12px 16px;margin:10px 0 14px 0;font-size:.92rem;display:flex;gap:10px;align-items:flex-start;}
.cb-caution svg{stroke:var(--warn-text);margin-top:2px;}
.cb-chip{display:inline-block;color:#fff;font-size:.72rem;font-weight:700;padding:2px 9px;border-radius:10px;}
.cb-pill{display:inline-block;background:var(--green);color:#fff;font-weight:600;padding:6px 16px;border-radius:18px;margin:8px 0 6px 0;}
.cb-live{display:inline-flex;align-items:center;gap:5px;color:var(--live);font-weight:800;font-size:.72rem;letter-spacing:.6px;}
.cb-live:before{content:"";width:8px;height:8px;border-radius:50%;background:var(--live);animation:rqpulse 1.4s infinite;}
@keyframes rqpulse{0%{opacity:1}50%{opacity:.25}100%{opacity:1}}

/* ---- hero ---- */
.rq-hero{display:flex;align-items:center;gap:22px;background:linear-gradient(120deg,var(--green) 0%,var(--green2) 100%);border-radius:12px;padding:22px 26px;margin:4px 0 14px 0;color:#fff;box-shadow:var(--shadow);}
.rq-hero img{height:92px;width:92px;border-radius:22px;box-shadow:0 4px 14px rgba(0,0,0,.35);}
.rq-hero .t{font-size:1.9rem;font-weight:800;line-height:1.15;color:#fff;}
.rq-hero .s{font-size:1rem;opacity:.92;margin-top:4px;color:#fff;}

/* ---- match cards ---- */
.cb-strip{display:flex;gap:12px;overflow-x:auto;padding-bottom:8px;}
.cb-card{flex:0 0 300px;background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden;color:var(--text);box-shadow:var(--shadow);}
.cb-grid .cb-card{flex:none;width:100%;}
.cb-card-top{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:12px 14px 4px 14px;color:var(--muted);font-size:.78rem;}
.cb-card-top span.t{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:210px;}
.cb-team{display:flex;justify-content:space-between;padding:7px 14px;font-size:1.02rem;font-weight:700;color:var(--text);}
.cb-team.dim{color:var(--muted);font-weight:500;}
.cb-status{padding:6px 14px 12px 14px;color:var(--link);font-size:.9rem;min-height:1.4em;}
.cb-status.live{color:var(--live);font-weight:600;}
.cb-card-foot{background:var(--card2);padding:8px 14px;font-size:.75rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}

/* ---- stats, profile, news ---- */
.cb-stats{display:flex;gap:12px;flex-wrap:wrap;margin:6px 0 4px 0;}
.cb-stat{flex:1 1 150px;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 16px;box-shadow:var(--shadow);}
.cb-stat .v{font-size:1.55rem;font-weight:800;color:var(--text);}
.cb-stat .l{font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;display:flex;align-items:center;gap:6px;}
.rq-profile{display:flex;align-items:center;gap:18px;background:var(--card);border:1px solid var(--border);border-left:5px solid var(--green);border-radius:8px;padding:16px 18px;margin-bottom:12px;box-shadow:var(--shadow);}
.rq-avatar{width:68px;height:68px;border-radius:50%;background:var(--green);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.5rem;flex:none;}
.rq-profile .n{font-size:1.5rem;font-weight:800;color:var(--text);}
.rq-profile .m{color:var(--muted);font-size:.92rem;margin-top:2px;}
.rq-news{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:10px;box-shadow:var(--shadow);}
.rq-news .h{font-size:1.05rem;font-weight:700;color:var(--text);margin-bottom:4px;}
.rq-news .i{color:var(--muted);font-size:.92rem;}
.rq-news .d{color:var(--muted);font-size:.74rem;margin-top:6px;text-transform:uppercase;letter-spacing:.4px;}
.rq-footer{margin-top:28px;padding:14px 4px;border-top:1px solid var(--border);color:var(--muted);font-size:.78rem;text-align:center;}

/* ---- scorecard / data tables ---- */
.cb-teambar{background:var(--green);color:#fff;display:flex;justify-content:space-between;padding:10px 14px;font-weight:700;border-radius:6px 6px 0 0;margin-top:10px;}
.cb-table-wrap{overflow:auto;border:1px solid var(--border);border-radius:6px;background:var(--card);margin-bottom:12px;}
table.cb-table{width:100%;border-collapse:collapse;font-size:.9rem;color:var(--text);}
table.cb-table thead th{position:sticky;top:0;background:var(--card2);color:var(--text);text-align:left;padding:9px 12px;font-weight:700;white-space:nowrap;border-bottom:1px solid var(--border);}
table.cb-table td{padding:8px 12px;border-bottom:1px solid var(--border);color:var(--text);white-space:nowrap;}
table.cb-table tbody tr:hover td{background:var(--card2);}
.cb-note{color:var(--muted);font-size:.85rem;margin:-4px 0 12px 2px;}
.cb-empty{color:var(--muted);padding:16px;}
.cb-comm{border-bottom:1px solid var(--border);padding:10px 4px;display:flex;gap:12px;}
.cb-comm .o{min-width:44px;font-weight:700;color:var(--text);}
.cb-comm .e{display:inline-block;font-size:.7rem;font-weight:800;padding:1px 7px;border-radius:9px;color:#fff;margin-bottom:3px;}
.cb-comm .e.FOUR{background:#046196;} .cb-comm .e.SIX{background:#73229b;} .cb-comm .e.WICKET{background:#ba0950;}
.cb-comm .x{color:var(--text);font-size:.93rem;line-height:1.45;}

/* ---- Streamlit widgets re-coloured ---- */
.stTabs [data-baseweb="tab-list"]{border-bottom:1px solid var(--border);gap:4px;}
.stTabs [data-baseweb="tab"]{background:transparent;}
.stTabs [data-baseweb="tab"] p{color:var(--muted)!important;font-weight:600;}
.stTabs [aria-selected="true"] p{color:var(--accent)!important;}
.stTabs [data-baseweb="tab-highlight"]{background:var(--accent);}
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{background:var(--green);color:#fff!important;border:0;border-radius:6px;font-weight:600;}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stFormSubmitButton"]>button:hover{filter:brightness(1.12);color:#fff!important;}
.stButton>button:disabled{background:var(--bar);color:var(--muted)!important;}
.stButton>button p,.stDownloadButton>button p,[data-testid="stFormSubmitButton"]>button p{color:#fff!important;}
/* form controls (selectors follow Streamlit's data-testid structure) */
[data-testid="stSelectbox"] > div > div,[data-testid="stMultiSelect"] > div > div,[data-testid="stTextInputRootElement"],[data-testid="stNumberInputContainer"],
[data-testid="stTextAreaRootElement"],[data-testid="stDateInputField"],[data-baseweb="select"]>div,[data-baseweb="input"],[data-baseweb="base-input"],[data-baseweb="textarea"]{
  background:var(--card2)!important;border:1px solid var(--border)!important;color:var(--text)!important;}
[data-testid="stTextInputField"],[data-testid="stNumberInputField"],.stTextInput input,.stTextArea textarea,.stNumberInput input,.stDateInput input,
[data-testid="stSelectbox"] input,[data-testid="stMultiSelect"] input{background:transparent!important;color:var(--text)!important;}
[data-testid="stSelectbox"] *,[data-testid="stMultiSelect"] *{color:var(--text);}
[data-testid="stSelectbox"] svg,[data-testid="stMultiSelect"] svg,[data-testid="stNumberInputContainer"] svg{fill:var(--muted);}
input::placeholder,textarea::placeholder{color:var(--muted)!important;opacity:.8!important;}
[role="listbox"],[data-testid="stSelectboxVirtualDropdown"],[data-baseweb="popover"] ul,[data-baseweb="menu"],[data-baseweb="popover"]{background:var(--card2)!important;color:var(--text)!important;border-color:var(--border)!important;}
[role="listbox"] li,[role="option"],[data-baseweb="popover"] li{background:transparent!important;color:var(--text)!important;}
[role="option"]:hover,[role="listbox"] li:hover,[data-baseweb="popover"] li:hover{background:var(--bar)!important;}
[data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"]{background:var(--card2)!important;color:var(--text)!important;}
[data-testid="stExpander"]{background:var(--card);border:1px solid var(--border);border-radius:8px;}
[data-testid="stExpander"] summary,[data-testid="stExpander"] summary *{color:var(--text);}
[data-testid="stForm"]{background:var(--card);border:1px solid var(--border);border-radius:8px;}
[data-testid="stCode"] pre,.stCodeBlock pre{background:var(--card2)!important;}
[data-testid="stCode"] code,.stCodeBlock code{color:var(--text)!important;}
[data-testid="stAlert"]{border-radius:8px;}
[data-testid="stProgress"] div[role="progressbar"] > div{background:var(--accent);}
"""


# ============================================================================ theme state
def is_light() -> bool:
    """True when the user switched to the light theme (dark is the default)."""
    return bool(st.session_state.get("light_mode", False))


def palette() -> dict[str, str]:
    """Colours of the active mode."""
    return LIGHT if is_light() else DARK


def apply_theme() -> None:
    """Inject the CSS (variables for the active palette + the static rules)."""
    variables = ";".join(f"--{name}:{value}" for name, value in palette().items())
    st.markdown(
        f"<style>:root{{{variables}}}{_STATIC_CSS}</style>", unsafe_allow_html=True
    )


def _toggle_theme() -> None:
    """Button callback: flip between dark and light."""
    st.session_state["light_mode"] = not is_light()


def render_topbar() -> None:
    """Green navigation bar: logo, page links, 'More' menu and the theme switch."""
    with st.container(key="topbar"):
        widths = [2.0] + [1.0] * len(PAGES) + [1.1, 1.05]
        cols = st.columns(widths)
        cols[0].markdown(
            f'<div class="rq-brand"><img src="{logo_data_uri("small")}" alt="{APP_NAME} logo"><span>{APP_NAME}</span></div>',
            unsafe_allow_html=True,
        )
        for col, (path, label, symbol) in zip(cols[1 : len(PAGES) + 1], PAGES):
            col.page_link(path, label=label, icon=symbol)
        with cols[len(PAGES) + 1].popover("More", icon=":material/apps:"):
            for path, label, symbol in MORE_PAGES:
                st.page_link(path, label=label, icon=symbol)
        light = is_light()
        cols[len(PAGES) + 2].button(
            "Dark" if light else "Light",
            key="theme_btn",
            icon=":material/dark_mode:" if light else ":material/light_mode:",
            on_click=_toggle_theme,
        )


# ============================================================================ html helpers
def _one_line(markup: str) -> str:
    """Remove newlines/indentation so Markdown never mistakes HTML for a code block."""
    return "".join(line.strip() for line in markup.splitlines())


def esc(value: object) -> str:
    """HTML-escape any value (API text, names, ...)."""
    return html.escape("" if value is None else str(value))


def section(title: str, icon_name: str | None = None) -> None:
    """Green uppercase section heading (like 'LATEST NEWS')."""
    st.markdown(
        f'<div class="cb-section">{icon(icon_name, 18) if icon_name else ""}<span>{esc(title)}</span></div>',
        unsafe_allow_html=True,
    )


def page_title(title: str, subtitle: str = "", icon_name: str | None = None) -> None:
    """Big page title with a muted sub-line."""
    st.markdown(
        f'<div class="cb-title">{icon(icon_name, 28) if icon_name else ""}{esc(title)}</div><div class="cb-sub">{esc(subtitle)}</div>',
        unsafe_allow_html=True,
    )


def caution(text: str, label: str = "NOTE") -> None:
    """Orange-on-brown notice box (the 'CAUTION' style)."""
    st.markdown(
        f'<div class="cb-caution">{icon("alert", 18)}<div><b>{esc(label)}</b><br>{esc(text)}</div></div>',
        unsafe_allow_html=True,
    )


def pill(text: str) -> None:
    """Green rounded label (e.g. 'IND (1st Inn)')."""
    st.markdown(f'<span class="cb-pill">{esc(text)}</span>', unsafe_allow_html=True)


def note(text: str) -> None:
    """Small muted explanation under a table or chart."""
    st.markdown(f'<div class="cb-note">{esc(text)}</div>', unsafe_allow_html=True)


def format_chip(fmt: str) -> str:
    """Coloured chip HTML for Test / ODI / T20I."""
    return f'<span class="cb-chip" style="background:{FORMAT_COLORS.get(fmt, "#6b7378")}">{esc(fmt)}</span>'


def hero(title: str, subtitle: str) -> None:
    """Home-page banner with the RunIQ logo."""
    st.markdown(
        _one_line(
            f'<div class="rq-hero"><img src="{logo_data_uri("medium")}" alt="{APP_NAME}"><div><div class="t">{esc(title)}</div><div class="s">{esc(subtitle)}</div></div></div>'
        ),
        unsafe_allow_html=True,
    )


def stat_cards(items: list[tuple[str, object]] | list[tuple[str, object, str]]) -> None:
    """Row of statistic cards: ``[('Players', 150, 'users'), ...]`` (icon name optional)."""
    cards = ""
    for item in items:
        label, value = item[0], item[1]
        icon_name = item[2] if len(item) > 2 else None
        cards += f'<div class="cb-stat"><div class="v">{esc(value)}</div><div class="l">{icon(icon_name, 14) if icon_name else ""}{esc(label)}</div></div>'
    st.markdown(
        _one_line(f'<div class="cb-stats">{cards}</div>'), unsafe_allow_html=True
    )


def initials(name: str) -> str:
    """'V Kohli' -> 'VK'."""
    parts = [p for p in str(name).replace(".", " ").split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


def profile_header(name: str, lines: list[str], badge: str | None = None) -> None:
    """Player / team banner with an initials avatar."""
    meta = "".join(f'<div class="m">{esc(line)}</div>' for line in lines if line)
    chip = f'<div style="margin-top:6px">{badge}</div>' if badge else ""
    st.markdown(
        _one_line(
            f'<div class="rq-profile"><div class="rq-avatar">{esc(initials(name))}</div><div><div class="n">{esc(name)}</div>{meta}{chip}</div></div>'
        ),
        unsafe_allow_html=True,
    )


def news_card(headline: str, intro: str, meta: str) -> None:
    st.markdown(
        _one_line(
            f'<div class="rq-news"><div class="h">{esc(headline)}</div><div class="i">{esc(intro)}</div><div class="d">{esc(meta)}</div></div>'
        ),
        unsafe_allow_html=True,
    )


def footer() -> None:
    """Attribution line shown at the bottom of every page (licence requirement of the data sources)."""
    st.markdown(
        _one_line(
            f'<div class="rq-footer">{APP_NAME} · Historical data: <b>Cricsheet</b> (cricsheet.org, Open Data Commons Attribution License) · '
            "Live data: Cricbuzz Cricket API via RapidAPI · Not affiliated with Cricbuzz, ICC or any cricket board.</div>"
        ),
        unsafe_allow_html=True,
    )


def match_card_html(card: dict) -> str:
    """HTML for one match card. Keys: top, fmt, team1, score1, team2, score2, status, foot, winner (1|2|None), live (bool)."""
    winner, live = card.get("winner"), bool(card.get("live"))
    cls1, cls2 = (" dim" if winner == 2 else ""), (" dim" if winner == 1 else "")
    badge = (
        '<span class="cb-live">LIVE</span>'
        if live
        else format_chip(card.get("fmt", ""))
    )
    return (
        '<div class="cb-card">'
        f'<div class="cb-card-top"><span class="t">{esc(card.get("top"))}</span>{badge}</div>'
        f'<div class="cb-team{cls1}"><span>{esc(card.get("team1"))}</span><span>{esc(card.get("score1", ""))}</span></div>'
        f'<div class="cb-team{cls2}"><span>{esc(card.get("team2"))}</span><span>{esc(card.get("score2", ""))}</span></div>'
        f'<div class="cb-status{" live" if live else ""}">{esc(card.get("status"))}</div>'
        f'<div class="cb-card-foot">{esc(card.get("foot"))}</div></div>'
    )


def render_strip(cards: list[dict]) -> None:
    """Horizontally scrollable strip of match cards."""
    if not cards:
        st.markdown(
            '<div class="cb-panel cb-empty">No matches to show.</div>',
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        _one_line(
            '<div class="cb-strip">'
            + "".join(match_card_html(c) for c in cards)
            + "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_match_grid(
    cards: list[dict],
    key_prefix: str,
    columns: int = 3,
    open_label: str = "Match centre",
) -> None:
    """Cards in a grid, each with an 'open' button that jumps to the Match Centre page."""
    if not cards:
        st.markdown(
            '<div class="cb-panel cb-empty">No matches to show.</div>',
            unsafe_allow_html=True,
        )
        return
    for start in range(0, len(cards), columns):
        cols = st.columns(columns)
        for offset, card in enumerate(cards[start : start + columns]):
            with cols[offset]:
                st.markdown(
                    _one_line(f'<div class="cb-grid">{match_card_html(card)}</div>'),
                    unsafe_allow_html=True,
                )
                ref = card.get("ref")
                if ref and st.button(
                    open_label,
                    key=f"{key_prefix}_{start + offset}",
                    icon=":material/open_in_new:",
                ):
                    st.session_state["match_ref"] = (
                        ref  # read by pages/2_Match_Centre.py
                    )
                    st.switch_page("pages/2_Match_Centre.py")


def team_bar(left: str, right: str = "") -> None:
    """Green header bar above a scorecard table (team name + total)."""
    st.markdown(
        f'<div class="cb-teambar"><span>{esc(left)}</span><span>{esc(right)}</span></div>',
        unsafe_allow_html=True,
    )


_HEADER_WORDS = {
    "sr": "SR",
    "avg": "Avg",
    "econ": "Econ",
    "hs": "HS",
    "inns": "Inns",
    "ct": "Ct",
    "st": "St",
    "odi": "ODI",
    "t20i": "T20I",
    "lbw": "LBW",
    "id": "ID",
    "pct": "%",
    "std dev runs": "Std dev runs",
}


def _nice_header(name: object) -> str:
    """'avg_runs' -> 'Avg runs', 'sr' -> 'SR'. Mixed-case / numeric-looking names are left alone."""
    text = str(name)
    if not text.islower():
        return text
    spaced = text.replace("_", " ")
    return _HEADER_WORDS.get(spaced) or spaced.capitalize()


def render_table(
    df: pd.DataFrame | None,
    *,
    max_rows: int = 1000,
    max_height: int = 520,
    empty_message: str = "No data to show.",
) -> None:
    """Show a DataFrame as a Cricbuzz-style HTML table (all values are escaped)."""
    if df is None or df.empty:
        st.markdown(
            f'<div class="cb-panel cb-empty">{esc(empty_message)}</div>',
            unsafe_allow_html=True,
        )
        return
    df = df.rename(columns=_nice_header).copy()  # friendlier column titles
    for column in df.columns:  # None / NaN in text columns would print as "None"
        if df[column].dtype == object:
            df[column] = df[column].where(df[column].notna(), "–")
    body = df.head(max_rows).to_html(
        index=False,
        border=0,
        classes="cb-table",
        escape=True,
        na_rep="–",
        float_format=lambda x: f"{x:,.2f}",
    )
    extra = (
        f'<div class="cb-sub">Showing first {max_rows} of {len(df)} rows.</div>'
        if len(df) > max_rows
        else ""
    )
    st.markdown(
        _one_line(
            f'<div class="cb-table-wrap" style="max-height:{int(max_height)}px">{body}</div>{extra}'
        ),
        unsafe_allow_html=True,
    )


def style_figure(fig):
    """Make a Plotly figure follow the active palette."""
    p = palette()
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": p["text"]},
        colorway=CHART_COLORS,
        margin={"l": 20, "r": 10, "t": 50, "b": 20},
        legend={"font": {"color": p["text"]}},
        title={"font": {"color": p["accent"]}},
    )
    fig.update_xaxes(
        gridcolor=p["border"],
        zerolinecolor=p["border"],
        linecolor=p["border"],
        automargin=True,
    )  # automargin keeps tick labels visible
    fig.update_yaxes(
        gridcolor=p["border"],
        zerolinecolor=p["border"],
        linecolor=p["border"],
        automargin=True,
    )
    return fig


def show_chart(fig, key: str | None = None) -> None:
    """Render a themed Plotly chart."""
    st.plotly_chart(style_figure(fig), theme=None, key=key)
