"""
盤前監控 Pre-Market Monitor
美股盤前數據監控 | Fortune Trading Desk
v5: 全面升級 — st_autorefresh · 價位警報 · VIX歷史對比 · 深色模式
     · 恐懼貪婪指數 · 新聞手動刷新 · 週曆排序 · Prompt複製反饋
     · 殖利率 · 板塊輪動 · Fed/財報/中美intel · TSLA技術位
     · Telegram推送 · 相對強弱 · Put/Call Ratio
"""

import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, time, timedelta
import pytz
import time as time_module
import requests
import json
import os
import html as _html

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="盤前監控 Pre-Market",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Session state ─────────────────────────────────────────────────────────────
DEFAULTS = {
    "auto_refresh":          False,
    "refresh_interval":      60,
    "custom_tickers":        "",
    "serper_key":            os.environ.get("SERPER_API_KEY", ""),
    "groq_key":              os.environ.get("GROQ_API_KEY", ""),
    "weekly_events":         None,
    "weekly_events_fetched": "",
    "ai_prompt":             "",
    "show_prompt":           False,
    "dark_mode":             False,
    # price alerts
    "price_alerts":          [],
    "alert_ticker":          "TSLA",
    "alert_price":           "",
    "alert_dir":             "突破上方",
    # news panel manual-refresh timestamps
    "news_refresh":          {},
    # copy feedback
    "prompt_copied":         False,
    "prompt_copied_at":      0.0,
    # VIX yesterday cache
    "vix_prev":              None,
    "vix_prev_date":         "",
    # Telegram
    "tg_token":              os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "tg_chat_id":            os.environ.get("TELEGRAM_CHAT_ID", ""),
    "tg_sent_hashes":        set(),   # MD5 dedup
    "tg_vix_threshold":      25.0,
    "tg_tsla_pct_threshold": 3.0,
    "tg_yield_threshold":    4.5,
    # TSLA tech panel
    "tsla_shares":           100,
    "tech_period":           "3mo",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Theme helpers ─────────────────────────────────────────────────────────────
def _theme():
    if st.session_state.dark_mode:
        return {
            "--bg":"#1A1A1A","--bg2":"#141414","--card":"#222222","--border":"#333333",
            "--text":"#E8E4DC","--muted":"#7A7570","--accent":"#7A9E7E",
            "--up":"#4CAF7A","--up-bg":"#0D2B1A",
            "--down":"#E05252","--down-bg":"#2B0D0D",
            "--flat":"#7A7570","--flat-bg":"#2A2A2A",
        }
    return {
        "--bg":"#F5F1EA","--bg2":"#EDE8DF","--card":"#FAF7F2","--border":"#D8D0C0",
        "--text":"#2C2A25","--muted":"#8A8278","--accent":"#6B7C6E",
        "--up":"#3A7D5C","--up-bg":"#EAF4EE",
        "--down":"#C0392B","--down-bg":"#FDECEA",
        "--flat":"#8A8278","--flat-bg":"#F0EDE8",
    }


# ── CSS ───────────────────────────────────────────────────────────────────────
def inject_css():
    t = _theme()
    vars_css = "\n".join(f"    {k}:{v};" for k,v in t.items())
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=Noto+Sans+TC:wght@300;400;500;700&display=swap');
    :root {{
{vars_css}
        --mono:'IBM Plex Mono',monospace; --sans:'Noto Sans TC',sans-serif;
    }}
    html,body,[class*="css"]{{font-family:var(--sans);background-color:var(--bg)!important;color:var(--text);}}
    .stApp{{background-color:var(--bg)!important;}}
    #MainMenu,footer,header{{visibility:hidden;}}
    .block-container{{padding-top:1rem!important;}}

    .pm-header{{display:flex;align-items:baseline;justify-content:space-between;
        padding:1.2rem 0 0.6rem;border-bottom:2px solid var(--border);margin-bottom:1.2rem;}}
    .pm-title{{font-family:var(--mono);font-size:1.05rem;font-weight:600;
        letter-spacing:.08em;color:var(--accent);text-transform:uppercase;}}
    .pm-subtitle{{font-family:var(--sans);font-size:.82rem;color:var(--muted);margin-top:.15rem;}}
    .pm-clock{{font-family:var(--mono);font-size:.88rem;color:var(--muted);text-align:right;}}
    .pm-session-badge{{display:inline-block;font-family:var(--mono);font-size:.68rem;
        font-weight:600;letter-spacing:.1em;padding:.18rem .55rem;border-radius:3px;
        margin-left:.5rem;background:var(--accent);color:var(--bg);}}

    .section-label{{font-family:var(--mono);font-size:.68rem;font-weight:600;
        letter-spacing:.15em;color:var(--muted);text-transform:uppercase;
        margin:1.3rem 0 .65rem;padding-bottom:.28rem;border-bottom:1px solid var(--border);}}

    .quote-card{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.9rem 1.1rem;margin-bottom:.5rem;transition:box-shadow .2s;}}
    .quote-card:hover{{box-shadow:0 2px 12px rgba(0,0,0,.1);}}
    .quote-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.38rem;}}
    .quote-ticker{{font-family:var(--mono);font-size:.95rem;font-weight:600;color:var(--text);letter-spacing:.05em;}}
    .quote-name{{font-family:var(--sans);font-size:.7rem;color:var(--muted);margin-top:.1rem;}}
    .quote-price{{font-family:var(--mono);font-size:1.35rem;font-weight:600;text-align:right;}}
    .quote-change{{font-family:var(--mono);font-size:.78rem;font-weight:500;text-align:right;margin-top:.05rem;}}
    .quote-meta{{display:flex;gap:1rem;font-family:var(--mono);font-size:.67rem;
        color:var(--muted);padding-top:.45rem;border-top:1px solid var(--border);flex-wrap:wrap;}}
    .quote-meta span b{{color:var(--text);font-weight:500;}}

    .up{{color:var(--up);}} .down{{color:var(--down);}} .flat{{color:var(--flat);}}

    .pill{{display:inline-block;padding:.12rem .42rem;border-radius:3px;
        font-family:var(--mono);font-size:.62rem;font-weight:600;letter-spacing:.05em;}}
    .pill-up{{background:var(--up-bg);color:var(--up);}}
    .pill-down{{background:var(--down-bg);color:var(--down);}}
    .pill-flat{{background:var(--flat-bg);color:var(--flat);}}

    .mini-card{{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:.75rem 1rem;text-align:center;}}
    .mini-label{{font-family:var(--mono);font-size:.62rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:.28rem;}}
    .mini-value{{font-family:var(--mono);font-size:1.25rem;font-weight:600;}}
    .mini-sub{{font-family:var(--sans);font-size:.68rem;color:var(--muted);margin-top:.12rem;}}

    .alert-box{{background:var(--flat-bg);border-left:3px solid #D4A017;border-radius:0 4px 4px 0;
        padding:.55rem .9rem;font-family:var(--sans);font-size:.78rem;color:var(--text);margin-bottom:.5rem;}}

    .signal-badge{{display:inline-block;font-family:var(--mono);font-size:.6rem;font-weight:700;
        letter-spacing:.06em;padding:.12rem .45rem;border-radius:3px;margin-left:.4rem;}}
    .signal-bearish{{background:var(--down-bg);color:var(--down);}}
    .signal-bullish{{background:var(--up-bg);color:var(--up);}}
    .signal-neutral{{background:var(--flat-bg);color:var(--flat);}}

    /* PRICE ALERT BANNER */
    .price-alert-banner{{background:var(--down-bg);border:2px solid var(--down);border-radius:6px;
        padding:.7rem 1rem;font-family:var(--mono);font-size:.8rem;font-weight:600;
        color:var(--down);margin-bottom:.5rem;display:flex;align-items:center;gap:.6rem;
        animation:flashAlert 1s ease-in-out 3;}}
    @keyframes flashAlert{{0%,100%{{opacity:1;}}50%{{opacity:.4;}}}}

    /* FEAR & GREED */
    .fg-card{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.9rem 1.1rem;margin-bottom:.5rem;}}
    .fg-label{{font-family:var(--mono);font-size:.62rem;letter-spacing:.12em;text-transform:uppercase;
        color:var(--muted);margin-bottom:.5rem;}}
    .fg-meter{{width:100%;height:10px;border-radius:5px;background:linear-gradient(90deg,
        #C0392B 0%,#E67E22 25%,#F1C40F 50%,#27AE60 75%,#2ECC71 100%);
        margin:.4rem 0;position:relative;}}
    .fg-needle{{position:absolute;top:-3px;width:4px;height:16px;background:var(--text);
        border-radius:2px;transform:translateX(-50%);transition:left .5s;}}
    .fg-value{{font-family:var(--mono);font-size:1.4rem;font-weight:700;}}
    .fg-sentiment{{font-family:var(--sans);font-size:.75rem;color:var(--muted);margin-top:.12rem;}}

    /* VIX DELTA */
    .vix-delta{{font-family:var(--mono);font-size:.65rem;margin-top:.08rem;}}

    /* YIELD PANEL */
    .yield-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;margin-bottom:.5rem;}}
    .yield-card{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.7rem .9rem;text-align:center;}}
    .yield-label{{font-family:var(--mono);font-size:.58rem;letter-spacing:.1em;text-transform:uppercase;
        color:var(--muted);margin-bottom:.22rem;}}
    .yield-value{{font-family:var(--mono);font-size:1.18rem;font-weight:700;}}
    .yield-chg{{font-family:var(--mono);font-size:.68rem;margin-top:.06rem;}}
    .yield-signal{{font-family:var(--sans);font-size:.72rem;border-left:3px solid var(--border);
        padding:.45rem .85rem;margin-top:.4rem;border-radius:0 4px 4px 0;}}

    /* SECTOR ROTATION */
    .sector-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:.4rem;margin-bottom:.4rem;}}
    .sector-card{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.6rem .8rem;position:relative;overflow:hidden;}}
    .sector-bar{{position:absolute;bottom:0;left:0;height:3px;border-radius:0 0 0 0;transition:width .4s;}}
    .sector-name{{font-family:var(--mono);font-size:.6rem;font-weight:600;letter-spacing:.08em;
        text-transform:uppercase;color:var(--muted);margin-bottom:.18rem;}}
    .sector-etf{{font-family:var(--mono);font-size:.55rem;color:var(--muted);}}
    .sector-pct{{font-family:var(--mono);font-size:1.05rem;font-weight:700;margin:.12rem 0;}}
    .sector-rank{{position:absolute;top:.4rem;right:.55rem;font-family:var(--mono);
        font-size:.58rem;color:var(--muted);}}
    .sector-leader{{border-color:var(--up);box-shadow:0 0 0 1px var(--up-bg);}}
    .sector-laggard{{border-color:var(--down);box-shadow:0 0 0 1px var(--down-bg);}}
    .rotation-insight{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.65rem 1rem;font-family:var(--sans);font-size:.76rem;line-height:1.6;
        color:var(--text);margin-top:.3rem;}}

    /* CALENDAR */
    .cal-wrap{{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:.9rem 1.1rem;margin-bottom:.6rem;}}
    .cal-title{{font-family:var(--mono);font-size:.68rem;font-weight:700;letter-spacing:.15em;
        text-transform:uppercase;color:var(--accent);margin-bottom:.7rem;}}
    .cal-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:.4rem;}}
    .cal-day{{border:1px solid var(--border);border-radius:5px;padding:.55rem .65rem;background:var(--bg);}}
    .cal-day.today{{border-color:var(--accent);background:var(--card);box-shadow:0 0 0 2px rgba(107,124,110,.15);}}
    .cal-day.past{{opacity:.45;}}
    .cal-dayname{{font-family:var(--mono);font-size:.58rem;font-weight:700;letter-spacing:.1em;
        text-transform:uppercase;color:var(--muted);margin-bottom:.08rem;}}
    .cal-date{{font-family:var(--mono);font-size:.82rem;font-weight:600;color:var(--text);margin-bottom:.35rem;}}
    .cal-today-badge{{font-family:var(--mono);font-size:.52rem;font-weight:700;background:var(--accent);
        color:var(--bg);padding:.03rem .32rem;border-radius:2px;letter-spacing:.06em;margin-left:.28rem;}}
    .cal-event{{font-family:var(--sans);font-size:.66rem;line-height:1.4;margin-bottom:.22rem;
        display:flex;gap:.28rem;align-items:flex-start;}}
    .cal-dot{{width:5px;height:5px;border-radius:50%;flex-shrink:0;margin-top:.28rem;}}
    .cal-dot.red{{background:var(--down);}} .cal-dot.amber{{background:#D4A017;}}
    .cal-dot.green{{background:var(--up);}} .cal-dot.blue{{background:#2E6DA4;}}
    .cal-dot.purple{{background:#7B5EA7;}}
    .cal-impact{{font-family:var(--mono);font-size:.52rem;font-weight:700;padding:.03rem .28rem;
        border-radius:2px;white-space:nowrap;}}
    .imp-high{{background:var(--down-bg);color:var(--down);}}
    .imp-med{{background:#FFF8E8;color:#8B6000;}}
    .imp-low{{background:var(--flat-bg);color:var(--flat);}}
    .cal-alert-strip{{background:var(--down-bg);border-left:3px solid var(--down);border-radius:0 4px 4px 0;
        padding:.5rem .8rem;font-size:.76rem;color:var(--down);margin-top:.5rem;font-family:var(--sans);}}
    .cal-source{{font-family:var(--mono);font-size:.55rem;color:var(--muted);
        margin-top:.4rem;padding-top:.4rem;border-top:1px solid var(--border);}}

    /* TSLA TECHNICAL PANEL */
    .tech-wrap{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:1rem 1.15rem;margin-bottom:.5rem;}}
    .tech-header{{display:flex;justify-content:space-between;align-items:center;
        margin-bottom:.8rem;padding-bottom:.45rem;border-bottom:1px solid var(--border);}}
    .tech-title{{font-family:var(--mono);font-size:.72rem;font-weight:600;
        letter-spacing:.08em;color:var(--accent);text-transform:uppercase;}}
    .tech-price{{font-family:var(--mono);font-size:1.5rem;font-weight:700;}}
    .tech-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem;margin-bottom:.6rem;}}
    .tech-card{{background:var(--bg);border:1px solid var(--border);border-radius:5px;
        padding:.6rem .8rem;text-align:center;}}
    .tech-card.active{{border-color:var(--accent);background:var(--card);}}
    .tech-card.warn{{border-color:var(--down);background:var(--down-bg);}}
    .tech-clabel{{font-family:var(--mono);font-size:.55rem;letter-spacing:.1em;
        text-transform:uppercase;color:var(--muted);margin-bottom:.15rem;}}
    .tech-cval{{font-family:var(--mono);font-size:.92rem;font-weight:600;}}
    .tech-csub{{font-family:var(--mono);font-size:.58rem;color:var(--muted);margin-top:.06rem;}}
    .level-row{{display:flex;justify-content:space-between;align-items:center;
        padding:.3rem 0;border-bottom:1px dotted var(--border);font-family:var(--mono);font-size:.72rem;}}
    .level-row:last-child{{border-bottom:none;}}
    .level-label{{color:var(--muted);font-size:.62rem;letter-spacing:.06em;}}
    .level-zone{{font-family:var(--sans);font-size:.68rem;color:var(--muted);}}
    .gap-badge{{display:inline-block;font-family:var(--mono);font-size:.62rem;font-weight:700;
        padding:.15rem .5rem;border-radius:3px;margin-left:.4rem;}}
    .gap-up{{background:var(--up-bg);color:var(--up);}}
    .gap-down{{background:var(--down-bg);color:var(--down);}}
    .signal-row{{background:var(--bg2);border-radius:5px;padding:.55rem .8rem;
        font-family:var(--sans);font-size:.76rem;line-height:1.65;margin-top:.5rem;}}

    /* RELATIVE STRENGTH */
    .rs-wrap{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.9rem 1.1rem;margin-bottom:.5rem;}}
    .rs-header{{display:flex;justify-content:space-between;align-items:center;
        margin-bottom:.7rem;padding-bottom:.38rem;border-bottom:1px solid var(--border);}}
    .rs-title{{font-family:var(--mono);font-size:.72rem;font-weight:600;
        letter-spacing:.08em;color:var(--accent);text-transform:uppercase;}}
    .rs-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;margin-bottom:.55rem;}}
    .rs-card{{background:var(--bg);border:1px solid var(--border);border-radius:5px;
        padding:.6rem .75rem;text-align:center;}}
    .rs-card.outperform{{border-color:var(--up);background:var(--up-bg);}}
    .rs-card.underperform{{border-color:var(--down);background:var(--down-bg);}}
    .rs-label{{font-family:var(--mono);font-size:.56rem;letter-spacing:.1em;
        text-transform:uppercase;color:var(--muted);margin-bottom:.14rem;}}
    .rs-val{{font-family:var(--mono);font-size:1.05rem;font-weight:700;}}
    .rs-sub{{font-family:var(--mono);font-size:.6rem;color:var(--muted);margin-top:.06rem;}}
    .rs-bar-wrap{{background:var(--border);border-radius:4px;height:6px;
        margin:.45rem 0 .3rem;position:relative;overflow:visible;}}
    .rs-bar-zero{{position:absolute;left:50%;top:-3px;width:2px;height:12px;
        background:var(--muted);border-radius:1px;}}
    .rs-bar-fill{{position:absolute;top:0;height:6px;border-radius:4px;transition:width .4s;}}
    .rs-verdict{{font-family:var(--sans);font-size:.76rem;line-height:1.65;
        padding:.5rem .8rem;border-radius:5px;background:var(--bg2);}}

    /* PUT/CALL RATIO */
    .pc-wrap{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.9rem 1.1rem;margin-bottom:.5rem;}}
    .pc-header{{display:flex;justify-content:space-between;align-items:center;
        margin-bottom:.65rem;padding-bottom:.38rem;border-bottom:1px solid var(--border);}}
    .pc-title{{font-family:var(--mono);font-size:.72rem;font-weight:600;
        letter-spacing:.08em;color:var(--accent);text-transform:uppercase;}}
    .pc-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem;margin-bottom:.5rem;}}
    .pc-card{{background:var(--bg);border:1px solid var(--border);border-radius:5px;
        padding:.65rem .85rem;text-align:center;}}
    .pc-card.extreme-fear{{border-color:var(--up);background:var(--up-bg);}}
    .pc-card.extreme-greed{{border-color:var(--down);background:var(--down-bg);}}
    .pc-card.neutral{{border-color:var(--accent);}}
    .pc-label{{font-family:var(--mono);font-size:.56rem;letter-spacing:.1em;
        text-transform:uppercase;color:var(--muted);margin-bottom:.14rem;}}
    .pc-val{{font-family:var(--mono);font-size:1.28rem;font-weight:700;}}
    .pc-sub{{font-family:var(--mono);font-size:.6rem;color:var(--muted);margin-top:.06rem;}}
    .pc-meter{{width:100%;height:8px;border-radius:4px;
        background:linear-gradient(90deg,var(--up) 0%,var(--flat-bg) 40%,var(--flat-bg) 60%,var(--down) 100%);
        margin:.38rem 0;position:relative;}}
    .pc-needle{{position:absolute;top:-4px;width:4px;height:16px;
        background:var(--text);border-radius:2px;transform:translateX(-50%);transition:left .5s;}}
    .pc-signal{{font-family:var(--sans);font-size:.76rem;padding:.5rem .8rem;
        border-radius:5px;line-height:1.65;}}

    /* TELEGRAM PANEL */
    .tg-panel{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.8rem 1rem;margin-bottom:.5rem;}}
    .tg-log{{font-family:var(--mono);font-size:.65rem;color:var(--muted);
        max-height:120px;overflow-y:auto;padding:.4rem .6rem;
        background:var(--bg);border-radius:4px;margin-top:.4rem;border:1px solid var(--border);}}
    .tg-log-item{{padding:.12rem 0;border-bottom:1px dotted var(--border);}}
    .tg-log-item:last-child{{border-bottom:none;}}

    /* DXY + BTC PANEL */
    .macro-lead-wrap{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.9rem 1.1rem;margin-bottom:.5rem;}}
    .macro-lead-header{{display:flex;justify-content:space-between;align-items:center;
        margin-bottom:.7rem;padding-bottom:.38rem;border-bottom:1px solid var(--border);}}
    .macro-lead-title{{font-family:var(--mono);font-size:.72rem;font-weight:600;
        letter-spacing:.08em;color:var(--accent);text-transform:uppercase;}}
    .macro-lead-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;margin-bottom:.5rem;}}
    .macro-card{{background:var(--bg);border:1px solid var(--border);border-radius:5px;
        padding:.7rem .9rem;text-align:center;position:relative;overflow:hidden;}}
    .macro-card.risk-off{{border-color:var(--down);box-shadow:0 0 0 1px var(--down-bg);}}
    .macro-card.risk-on{{border-color:var(--up);box-shadow:0 0 0 1px var(--up-bg);}}
    .macro-clabel{{font-family:var(--mono);font-size:.56rem;letter-spacing:.12em;
        text-transform:uppercase;color:var(--muted);margin-bottom:.18rem;}}
    .macro-cval{{font-family:var(--mono);font-size:1.15rem;font-weight:700;}}
    .macro-chg{{font-family:var(--mono);font-size:.68rem;margin-top:.06rem;}}
    .macro-meta{{font-family:var(--mono);font-size:.58rem;color:var(--muted);
        margin-top:.22rem;padding-top:.22rem;border-top:1px dotted var(--border);}}
    .macro-corr-badge{{position:absolute;top:.35rem;right:.45rem;font-family:var(--mono);
        font-size:.52rem;font-weight:700;padding:.08rem .32rem;border-radius:2px;}}
    .corr-inv{{background:var(--down-bg);color:var(--down);}}
    .corr-pos{{background:var(--up-bg);color:var(--up);}}
    .macro-signal{{font-family:var(--sans);font-size:.76rem;line-height:1.65;
        padding:.5rem .85rem;border-radius:5px;border-left:3px solid var(--border);}}
    .macro-divider{{height:1px;background:var(--border);margin:.45rem 0;}}
    .macro-spark{{font-family:var(--mono);font-size:.58rem;color:var(--muted);
        margin-top:.1rem;letter-spacing:.02em;}}

    .oil-card{{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:.75rem 1rem;}}
    .oil-label{{font-family:var(--mono);font-size:.6rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:.22rem;}}
    .oil-price{{font-family:var(--mono);font-size:1.28rem;font-weight:600;}}
    .oil-chg{{font-family:var(--mono);font-size:.7rem;margin-top:.08rem;}}
    .oil-meta{{font-family:var(--mono);font-size:.6rem;color:var(--muted);margin-top:.28rem;}}

    .intel-panel{{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:1rem 1.15rem;margin-bottom:.55rem;}}
    .intel-header{{display:flex;justify-content:space-between;align-items:center;
        margin-bottom:.7rem;padding-bottom:.45rem;border-bottom:1px solid var(--border);}}
    .intel-title{{font-family:var(--mono);font-size:.72rem;font-weight:600;letter-spacing:.08em;color:var(--accent);text-transform:uppercase;}}
    .intel-time{{font-family:var(--mono);font-size:.6rem;color:var(--muted);}}
    .intel-summary{{font-family:var(--sans);font-size:.8rem;line-height:1.7;color:var(--text);margin-bottom:.75rem;}}
    .news-item{{display:flex;gap:.65rem;padding:.45rem 0;border-bottom:1px solid var(--border);align-items:flex-start;}}
    .news-item:last-child{{border-bottom:none;}}
    .news-dot{{width:6px;height:6px;border-radius:50%;background:var(--accent);margin-top:.32rem;flex-shrink:0;}}
    .news-dot.red{{background:var(--down);}} .news-dot.amber{{background:#D4A017;}}
    .news-text{{font-family:var(--sans);font-size:.76rem;line-height:1.5;color:var(--text);}}
    .news-source{{font-family:var(--mono);font-size:.58rem;color:var(--muted);margin-top:.08rem;}}

    .prompt-panel{{background:var(--bg2);border:1px solid var(--border);border-radius:6px;
        padding:1rem 1.15rem;margin-top:.5rem;}}
    .prompt-title{{font-family:var(--mono);font-size:.68rem;font-weight:700;letter-spacing:.1em;
        text-transform:uppercase;color:var(--accent);margin-bottom:.6rem;}}

    /* COPY TOAST */
    .copy-toast{{background:var(--up-bg);border:1px solid var(--up);border-radius:4px;
        padding:.35rem .75rem;font-family:var(--mono);font-size:.7rem;color:var(--up);
        display:inline-block;margin-left:.8rem;}}

    /* ALERT PANEL */
    .alert-panel{{background:var(--card);border:1px solid var(--border);border-radius:6px;
        padding:.8rem 1rem;margin-bottom:.5rem;}}
    .alert-row{{display:flex;justify-content:space-between;align-items:center;
        padding:.3rem 0;border-bottom:1px solid var(--border);font-family:var(--mono);font-size:.72rem;}}
    .alert-row:last-child{{border-bottom:none;}}

    .stButton>button{{font-family:var(--mono)!important;font-size:.73rem!important;
        letter-spacing:.08em!important;background:var(--accent)!important;color:var(--bg)!important;
        border:none!important;border-radius:4px!important;padding:.38rem 1rem!important;}}
    [data-testid="stSidebar"]{{background:var(--bg2)!important;border-right:1px solid var(--border);}}
    </style>
    """, unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_num(n, d=2):
    return "—" if n is None else f"{n:,.{d}f}"

def fmt_pct(n):
    if n is None: return "—"
    return ("+" if n >= 0 else "") + f"{n:.2f}%"

def fmt_vol(n):
    if not n: return "—"
    if n >= 1e6: return f"{n/1e6:.1f}M"
    if n >= 1e3: return f"{n/1e3:.0f}K"
    return str(n)

def fmt_cap(n):
    if not n: return "—"
    if n >= 1e12: return f"${n/1e12:.2f}T"
    if n >= 1e9:  return f"${n/1e9:.1f}B"
    return f"${n/1e6:.0f}M"

def cc(v):
    return "flat" if v is None else ("up" if v > 0 else ("down" if v < 0 else "flat"))

def pc(v):
    return "pill-flat" if v is None else ("pill-up" if v > 0 else ("pill-down" if v < 0 else "pill-flat"))

def get_session_info():
    et = pytz.timezone("America/New_York")
    now_et = datetime.now(et)
    t = now_et.time()
    if   time(4,0)  <= t < time(9,30):  session = "盤前 PRE-MARKET"
    elif time(9,30) <= t < time(16,0):  session = "盤中 REGULAR"
    elif time(16,0) <= t < time(20,0):  session = "盤後 AFTER-HOURS"
    elif time(20,0) <= t or t < time(4,0): session = "隔夜 OVERNIGHT"
    else:                                session = "休市 CLOSED"
    return now_et, session

def week_monday_str():
    et = pytz.timezone("America/New_York")
    today = datetime.now(et).date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()

def _today_et_str():
    return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")


# ── Quote fetching ────────────────────────────────────────────────────────────
def _yahoo_chart_api(ticker: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"interval":"1m","range":"1d","includePrePost":"true","corsDomain":"finance.yahoo.com"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://finance.yahoo.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        from curl_cffi import requests as curl_req
        resp = curl_req.get(url, params=params, headers=headers, impersonate="chrome124", timeout=12)
    except Exception:
        resp = requests.get(url, params=params, headers=headers, timeout=12)

    data   = resp.json()
    result = data["chart"]["result"][0]
    meta   = result["meta"]
    price  = meta.get("regularMarketPrice") or meta.get("previousClose")
    prev   = meta.get("chartPreviousClose") or meta.get("previousClose") or price
    pre_price  = meta.get("preMarketPrice")
    post_price = meta.get("postMarketPrice")

    et     = pytz.timezone("America/New_York")
    today  = datetime.now(et).date()
    day_high = day_low = volume = avg_vol = None
    try:
        timestamps = result.get("timestamp", [])
        closes  = result["indicators"]["quote"][0].get("close",  [])
        highs   = result["indicators"]["quote"][0].get("high",   [])
        lows    = result["indicators"]["quote"][0].get("low",    [])
        volumes = result["indicators"]["quote"][0].get("volume", [])
        pre_bars = []; post_bars = []
        reg_highs = []; reg_lows = []; reg_vols = []
        for i, ts in enumerate(timestamps):
            cl = closes[i]  if i < len(closes)  else None
            hi = highs[i]   if i < len(highs)   else None
            lo = lows[i]    if i < len(lows)     else None
            vo = volumes[i] if i < len(volumes)  else None
            if cl is None: continue
            dt = datetime.fromtimestamp(ts, tz=et)
            if dt.date() != today: continue
            t = dt.time()
            if t < time(9, 30):               pre_bars.append(cl)
            elif time(9,30) <= t < time(16,0):
                if hi: reg_highs.append(hi)
                if lo: reg_lows.append(lo)
                if vo: reg_vols.append(vo)
            elif time(16,0) <= t < time(20,0): post_bars.append(cl)
        if pre_bars  and pre_price  is None: pre_price  = pre_bars[-1]
        if post_bars and post_price is None: post_price = post_bars[-1]
        day_high = max(reg_highs) if reg_highs else None
        day_low  = min(reg_lows)  if reg_lows  else None
        volume   = sum(reg_vols)  if reg_vols  else None
        frac = len(reg_vols) / 390.0
        avg_vol = int(volume / frac) if (volume and frac > 0.05) else None
    except Exception:
        pass

    def _cp(p, base):
        if p and base: return p - base, (p - base) / base * 100
        return None, None

    pre_chg,  pre_pct  = _cp(pre_price,  prev)
    post_chg, post_pct = _cp(post_price, price or prev)
    reg_chg,  reg_pct  = _cp(price, prev)
    return dict(
        ticker=ticker, name=meta.get("longName") or meta.get("shortName") or ticker,
        price=price, prev=prev, reg_chg=reg_chg, reg_pct=reg_pct,
        pre_price=pre_price, pre_chg=pre_chg, pre_pct=pre_pct,
        post_price=post_price, post_chg=post_chg, post_pct=post_pct,
        high=day_high, low=day_low, volume=volume, avg_vol=avg_vol, cap=None, error=None,
    )


def _yf_download_fallback(ticker: str) -> dict:
    df = yf.download(ticker, period="5d", interval="1m", prepost=True, progress=False, auto_adjust=True)
    if df.empty: raise RuntimeError("download returned empty")
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    et = pytz.timezone("America/New_York")
    today = datetime.now(et).date()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None: df.index = df.index.tz_localize("UTC").tz_convert(et)
    else: df.index = df.index.tz_convert(et)
    today_df = df[df.index.date == today]
    pre_df   = today_df[today_df.index.time < time(9, 30)]
    reg_df   = today_df[(today_df.index.time >= time(9,30)) & (today_df.index.time < time(16,0))]
    post_df  = today_df[today_df.index.time >= time(16, 0)]
    prev_df  = df[df.index.date < today]
    def _last(d, col="Close"):
        return float(d[col].iloc[-1]) if not d.empty and col in d.columns else None
    prev_close = _last(prev_df); reg_price = _last(reg_df) or _last(today_df)
    pre_price = _last(pre_df);   post_price = _last(post_df)
    def _cp(p, base):
        if p and base: return p - base, (p - base) / base * 100
        return None, None
    pre_chg,pre_pct   = _cp(pre_price, prev_close)
    post_chg,post_pct = _cp(post_price, reg_price or prev_close)
    reg_chg,reg_pct   = _cp(reg_price, prev_close)
    return dict(ticker=ticker, name=ticker, price=reg_price or prev_close, prev=prev_close,
                reg_chg=reg_chg, reg_pct=reg_pct, pre_price=pre_price, pre_chg=pre_chg, pre_pct=pre_pct,
                post_price=post_price, post_chg=post_chg, post_pct=post_pct,
                high=None, low=None, volume=None, avg_vol=None, cap=None, error=None)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_quote(ticker: str) -> dict:
    try: return _yahoo_chart_api(ticker)
    except Exception: pass
    if not (ticker.endswith("=F") or ticker.startswith("^")):
        try:
            from curl_cffi import requests as curl_req
            sess = curl_req.Session(impersonate="chrome110")
            t = yf.Ticker(ticker, session=sess); info = t.info
            if info.get("regularMarketPrice") or info.get("previousClose"):
                price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
                prev  = info.get("previousClose") or price
                pre_price  = info.get("preMarketPrice")
                pre_chg    = info.get("preMarketChange")
                pre_pct    = info.get("preMarketChangePercent")
                post_price = info.get("postMarketPrice")
                post_chg   = info.get("postMarketChange")
                post_pct   = info.get("postMarketChangePercent")
                if pre_pct  and abs(pre_pct)  < 1: pre_pct  *= 100
                if post_pct and abs(post_pct) < 1: post_pct *= 100
                reg_chg = (price - prev) if (price and prev) else None
                reg_pct = (reg_chg / prev * 100) if (reg_chg and prev) else None
                return dict(ticker=ticker, name=info.get("shortName") or ticker,
                            price=price, prev=prev, reg_chg=reg_chg, reg_pct=reg_pct,
                            pre_price=pre_price, pre_chg=pre_chg, pre_pct=pre_pct,
                            post_price=post_price, post_chg=post_chg, post_pct=post_pct,
                            high=info.get("dayHigh"), low=info.get("dayLow"),
                            volume=info.get("volume"), avg_vol=info.get("averageVolume"),
                            cap=info.get("marketCap"), error=None)
        except Exception: pass
    try: return _yf_download_fallback(ticker)
    except Exception as e: return dict(ticker=ticker, error=str(e))


def render_quote_card(data, is_pre, is_post):
    if data.get("error"):
        st.markdown(f'<div class="quote-card"><div class="quote-ticker">{data["ticker"]}</div>'
                    '<div class="quote-name" style="color:var(--down)">載入失敗</div></div>',
                    unsafe_allow_html=True)
        return
    pm_price=data.get("pre_price"); pm_chg=data.get("pre_chg"); pm_pct=data.get("pre_pct")
    ah_price=data.get("post_price"); ah_chg=data.get("post_chg"); ah_pct=data.get("post_pct")
    reg_price=data.get("price"); reg_chg=data.get("reg_chg"); reg_pct=data.get("reg_pct")
    isFut = data["ticker"].endswith("=F")
    t_now = datetime.now(pytz.timezone("America/New_York")).time()
    is_regular = time(9,30) <= t_now < time(16,0)
    if is_pre and pm_price:   dp,dc,dpct,lbl = pm_price,pm_chg,pm_pct,"盤前"
    elif is_post and ah_price: dp,dc,dpct,lbl = ah_price,ah_chg,ah_pct,"盤後"
    elif is_regular or isFut: dp,dc,dpct,lbl = reg_price,reg_chg,reg_pct,"盤中" if is_regular else "即時"
    else:                      dp,dc,dpct,lbl = reg_price,reg_chg,reg_pct,"收盤"
    sign    = "+" if (dc or 0) >= 0 else ""
    chg_str = f"{sign}{fmt_num(dc)} ({fmt_pct(dpct)})" if dc is not None else "—"
    vol,avg = data.get("volume"),data.get("avg_vol")
    vol_ratio = f"{vol/avg:.1f}x" if (vol and avg) else "—"
    vol_cls = "down" if (vol and avg and vol/avg>1.5) else ("up" if (vol and avg and vol/avg>1.0) else "flat")

    # FIX #3: dynamic color for pre/post price in meta row
    pm_cls = cc(pm_pct) if pm_pct is not None else "flat"
    ah_cls = cc(ah_pct) if ah_pct is not None else "flat"

    meta_parts = [f'<span>收盤 <b>{fmt_num(reg_price)}</b></span>']
    if pm_price: meta_parts.append(f'<span>盤前 <b class="{pm_cls}">{fmt_num(pm_price)}</b></span>')
    if ah_price: meta_parts.append(f'<span>盤後 <b class="{ah_cls}">{fmt_num(ah_price)}</b></span>')
    meta_parts += [
        f'<span>高 <b>{fmt_num(data.get("high"))}</b></span>',
        f'<span>低 <b>{fmt_num(data.get("low"))}</b></span>',
        f'<span>量 <b class="{vol_cls}">{fmt_vol(vol)}</b></span>',
        f'<span>量比 <b class="{vol_cls}">{vol_ratio}</b></span>',
        f'<span>市值 <b>{fmt_cap(data.get("cap"))}</b></span>',
    ]
    # Check price alerts for this ticker
    alert_html = _check_price_alert_inline(data["ticker"], dp)
    st.markdown(
        f'<div class="quote-card">'
        f'<div class="quote-top"><div>'
        f'<div class="quote-ticker">{data["ticker"]} '
        f'<span class="pill {pc(dpct)}" style="font-size:.58rem;margin-left:.35rem">{lbl}</span></div>'
        f'<div class="quote-name">{data["name"]}</div></div>'
        f'<div><div class="quote-price {cc(dpct)}">{fmt_num(dp)}</div>'
        f'<div class="quote-change {cc(dpct)}">{chg_str}</div></div></div>'
        f'<div class="quote-meta">{" ".join(meta_parts)}</div>'
        f'{alert_html}</div>',
        unsafe_allow_html=True)


# ── Groq AI call ──────────────────────────────────────────────────────────────
def groq_chat(prompt: str, groq_key: str, model: str = "llama-3.3-70b-versatile",
              max_tokens: int = 1200, temperature: float = 0.3) -> str:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
        json={"model": model, "max_tokens": max_tokens, "temperature": temperature,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=25,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── FIX #1: st_autorefresh — non-blocking ─────────────────────────────────────
def setup_autorefresh():
    """Use streamlit-autorefresh if available, else show a warning."""
    if not st.session_state.auto_refresh:
        return
    interval_ms = st.session_state.refresh_interval * 1000
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=interval_ms, key="auto_refresh_ticker")
    except ImportError:
        # Fallback: JS-based meta refresh (non-blocking, no sleep)
        st.markdown(
            f'<meta http-equiv="refresh" content="{st.session_state.refresh_interval}">',
            unsafe_allow_html=True)


# ── FIX #5: TSLA price alert system ──────────────────────────────────────────
def _check_price_alert_inline(ticker: str, current_price) -> str:
    """Return HTML alert strip if a price alert is triggered for this ticker."""
    if current_price is None: return ""
    fired = []
    for a in st.session_state.price_alerts:
        if a["ticker"].upper() != ticker.upper(): continue
        target = a["price"]
        direction = a["direction"]
        if direction == "突破上方" and current_price >= target:
            fired.append(f'🔔 {ticker} 突破 ${target:.2f} ↑ 現價 ${current_price:.2f}')
        elif direction == "跌破下方" and current_price <= target:
            fired.append(f'🔔 {ticker} 跌破 ${target:.2f} ↓ 現價 ${current_price:.2f}')
    if not fired: return ""
    msgs = " &nbsp;|&nbsp; ".join(fired)
    return f'<div class="price-alert-banner">🚨 {msgs}</div>'

def render_alert_manager():
    """Sidebar alert management UI."""
    st.markdown("### 🔔 價位警報")
    c1,c2,c3 = st.columns([2,2,2])
    with c1:
        ticker_in = st.text_input("代號", value=st.session_state.alert_ticker,
                                   key="alert_ticker_input", placeholder="TSLA").upper()
        st.session_state.alert_ticker = ticker_in
    with c2:
        price_in = st.text_input("價位 $", value=st.session_state.alert_price,
                                  key="alert_price_input", placeholder="400.00")
        st.session_state.alert_price = price_in
    with c3:
        dir_in = st.selectbox("方向", ["突破上方","跌破下方"], key="alert_dir_select")
        st.session_state.alert_dir = dir_in

    if st.button("➕ 加入警報", key="add_alert_btn"):
        try:
            p = float(price_in.replace("$","").replace(",",""))
            new_alert = {"ticker": ticker_in, "direction": dir_in, "price": p}
            # Avoid duplicate
            if new_alert not in st.session_state.price_alerts:
                st.session_state.price_alerts.append(new_alert)
                st.success(f"✅ 已設定：{ticker_in} {dir_in} ${p:.2f}")
        except ValueError:
            st.error("請輸入有效價位數字")

    if st.session_state.price_alerts:
        for i, a in enumerate(st.session_state.price_alerts):
            col_a, col_b = st.columns([4,1])
            with col_a:
                st.markdown(
                    f'<div style="font-family:var(--mono,monospace);font-size:.7rem;'
                    f'color:var(--text,#2C2A25);padding:.2rem 0">'
                    f'{a["ticker"]} {a["direction"]} <b>${a["price"]:.2f}</b></div>',
                    unsafe_allow_html=True)
            with col_b:
                if st.button("✕", key=f"del_alert_{i}"):
                    st.session_state.price_alerts.pop(i)
                    st.rerun()


# ── FIX #8: VIX yesterday fetch ───────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_vix_prev() -> float | None:
    """Fetch yesterday's VIX close for delta display."""
    try:
        df = yf.download("^VIX", period="5d", interval="1d", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if len(df) >= 2:
            return float(df["Close"].iloc[-2])
    except Exception:
        pass
    return None


# ── FIX #9: Fear & Greed Index ────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_fear_greed() -> dict:
    """
    CNN Fear & Greed Index via alternative.me (free, no key needed).
    Returns {"value": int, "classification": str, "prev_close": int}
    """
    try:
        r = requests.get("https://fear-and-greed-index.p.rapidapi.com/v1/fgi",
                         timeout=6)
    except Exception:
        r = None
    # Try alternative.me (more reliable, truly free)
    try:
        r2 = requests.get("https://api.alternative.me/fng/?limit=2", timeout=6)
        data = r2.json()["data"]
        current = int(data[0]["value"])
        prev    = int(data[1]["value"]) if len(data) > 1 else current
        label   = data[0]["value_classification"]
        return {"value": current, "classification": label, "prev": prev, "source": "alternative.me"}
    except Exception:
        pass
    return {"value": None, "classification": "N/A", "prev": None, "source": "N/A"}

def render_fear_greed():
    fg = fetch_fear_greed()
    val = fg.get("value")
    prev = fg.get("prev")
    label_map = {
        "Extreme Fear":"極度恐懼","Fear":"恐懼","Neutral":"中性",
        "Greed":"貪婪","Extreme Greed":"極度貪婪"
    }
    label_zh = label_map.get(fg.get("classification",""), fg.get("classification","—"))

    if val is None:
        st.markdown('<div class="fg-card"><div class="fg-label">恐懼貪婪指數</div>'
                    '<div class="fg-value flat">—</div></div>', unsafe_allow_html=True)
        return

    # Color based on value
    if   val <= 25: fg_col = "var(--down)"
    elif val <= 45: fg_col = "#E67E22"
    elif val <= 55: fg_col = "#F1C40F"
    elif val <= 75: fg_col = "#27AE60"
    else:           fg_col = "var(--up)"

    delta_str = ""
    if prev is not None:
        d = val - prev
        delta_str = f'<span style="font-size:.65rem;color:{"var(--up)" if d>=0 else "var(--down)"}">'
        delta_str += f'{"+" if d>=0 else ""}{d} vs昨日</span>'

    needle_pct = val  # 0-100 maps directly to 0%-100%
    st.markdown(
        f'<div class="fg-card">'
        f'<div class="fg-label">😱 CNN 恐懼貪婪指數</div>'
        f'<div style="display:flex;align-items:baseline;gap:.5rem">'
        f'<div class="fg-value" style="color:{fg_col}">{val}</div>'
        f'<div class="fg-sentiment">{label_zh} &nbsp;{delta_str}</div></div>'
        f'<div class="fg-meter"><div class="fg-needle" style="left:{needle_pct}%"></div></div>'
        f'<div style="display:flex;justify-content:space-between;font-family:var(--mono,monospace);'
        f'font-size:.55rem;color:var(--muted,#8A8278);margin-top:.18rem">'
        f'<span>極度恐懼</span><span>恐懼</span><span>中性</span><span>貪婪</span><span>極度貪婪</span></div>'
        f'<div style="font-family:var(--mono,monospace);font-size:.55rem;color:var(--muted,#8A8278);'
        f'margin-top:.28rem">來源：alternative.me</div>'
        f'</div>',
        unsafe_allow_html=True)


# ── Weekly events — Groq auto-generate ───────────────────────────────────────
# ── US Economic Calendar Engine ───────────────────────────────────────────────
# Hardcoded BLS/BEA/Fed release rules — not dependent on Groq or news scraping
# Rule format: (month_pattern, week_of_month, weekday, time_et, label, color, impact, note)
# month_pattern: list of months (1-12), or "all", or "quarter_end_plus1"
# week_of_month: 1=first, 2=second, 3=third, 4=fourth
# weekday: 0=Mon ... 4=Fri

import calendar as _calendar

US_MARKET_HOLIDAYS = {
    # (month, day): name — fixed-date NYSE holidays
    (1, 1):   "元旦",
    (6, 19):  "六月節",
    (7, 4):   "獨立日",
    (11, 11): "退伍軍人節",
    (12, 25): "聖誕節",
}

def _build_observed(years=range(2024, 2030)) -> dict:
    """
    NYSE rule: if fixed holiday falls on Saturday → observe Friday;
    if Sunday → observe Monday.
    Returns {(year,month,day): "HolidayName(補假)"}.
    """
    from datetime import date as _d, timedelta as _td
    obs = {}
    for yr in years:
        for (mo, day), name in US_MARKET_HOLIDAYS.items():
            try: hdate = _d(yr, mo, day)
            except ValueError: continue
            if hdate.weekday() == 5:   # Saturday → Friday
                o = hdate - _td(days=1)
                obs[(o.year, o.month, o.day)] = f"{name}(補假/觀察日)"
            elif hdate.weekday() == 6: # Sunday → Monday
                o = hdate + _td(days=1)
                obs[(o.year, o.month, o.day)] = f"{name}(補假/觀察日)"
    return obs

_OBSERVED_HOLIDAYS = _build_observed()

def _is_us_holiday(d) -> str | None:
    """Return holiday name if NYSE is closed on this date (fixed or observed)."""
    return (US_MARKET_HOLIDAYS.get((d.month, d.day))
            or _OBSERVED_HOLIDAYS.get((d.year, d.month, d.day)))

def _nth_weekday(year: int, month: int, n: int, weekday: int):
    """Return the nth occurrence of weekday (0=Mon) in given year/month."""
    count = 0
    for day in range(1, _calendar.monthrange(year, month)[1] + 1):
        d = __import__('datetime').date(year, month, day)
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
    return None

def _next_business_day(d):
    """Return next business day after d (skip weekends + fixed holidays)."""
    nd = d + __import__('datetime').timedelta(days=1)
    while nd.weekday() >= 5 or _is_us_holiday(nd):
        nd += __import__('datetime').timedelta(days=1)
    return nd

def _prev_business_day(d):
    """Return previous business day before d."""
    pd = d - __import__('datetime').timedelta(days=1)
    while pd.weekday() >= 5 or _is_us_holiday(pd):
        pd -= __import__('datetime').timedelta(days=1)
    return pd

def _adjust_for_holiday(release_date):
    """
    BLS rule: if scheduled release falls on holiday/weekend,
    release moves to PREVIOUS business day.
    Returns (adjusted_date, was_adjusted, reason).
    """
    if release_date.weekday() >= 5:
        adj = _prev_business_day(release_date)
        return adj, True, f"週末提前至{adj.strftime('%-m/%-d')}"
    h = _is_us_holiday(release_date)
    if h:
        adj = _prev_business_day(release_date)
        return adj, True, f"{h}提前至{adj.strftime('%-m/%-d')}"
    # Also check: if next trading day is holiday and today would be last day → flag
    next_td = _next_business_day(release_date)
    if _is_us_holiday(next_td) or next_td.weekday() >= 5:
        return release_date, False, "長週末前最後交易日"
    return release_date, False, ""

def get_economic_calendar(year: int, month: int) -> list[dict]:
    """
    Generate hardcoded economic events for a given month.
    Returns list of {date, text, et_time, color, impact, note, official}.
    """
    events = []
    from datetime import date as _date, timedelta as _td

    # ── Non-Farm Payrolls (Employment Situation) ──
    # BLS: first Friday of each month, reference previous month
    nfp_date = _nth_weekday(year, month, 1, 4)  # first Friday
    if nfp_date:
        adj_date, adjusted, reason = _adjust_for_holiday(nfp_date)
        prev_month = (month - 2) % 12 + 1
        prev_month_name = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"][prev_month-1]
        adj_note = f"（{reason}）" if reason else ""
        events.append(dict(
            date    = adj_date,
            text    = f"{prev_month_name}非農就業報告{adj_note}",
            et_time = "08:30",
            color   = "red",
            impact  = "high",
            note    = f"BLS官方發布{adj_note}。非農+失業率+薪資增長三合一，Fed最重視的就業數據，直接影響下次FOMC。偏強→加息預期升→科技/TSLA承壓；偏弱→降息預期→科技升。",
            official= "BLS",
        ))

    # ── CPI (Consumer Price Index) ──
    # BLS: approx 2nd or 3rd week, varies; use 2nd Wed as approximation
    # Actually BLS schedules vary — use known pattern: ~10-13 days after month end
    # Approximate: 2nd Wednesday
    cpi_approx = _nth_weekday(year, month, 2, 2)  # 2nd Wednesday
    if cpi_approx:
        adj_date, _, reason = _adjust_for_holiday(cpi_approx)
        prev_month_name = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"][(month-2)%12]
        events.append(dict(
            date    = adj_date,
            text    = f"{prev_month_name} CPI 消費者物價指數",
            et_time = "08:30",
            color   = "red",
            impact  = "high",
            note    = "通脹最關鍵指標。YoY高於預期→債息升/科技跌；低於預期→降息預期→科技/TSLA升。",
            official= "BLS",
        ))

    # ── PPI ── approx 1 day after CPI (Thursday)
    ppi_approx = _nth_weekday(year, month, 2, 3)  # 2nd Thursday
    if ppi_approx:
        adj_date, _, reason = _adjust_for_holiday(ppi_approx)
        prev_month_name = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"][(month-2)%12]
        events.append(dict(
            date    = adj_date,
            text    = f"{prev_month_name} PPI 生產者物價指數",
            et_time = "08:30",
            color   = "amber",
            impact  = "med",
            note    = "上游通脹指標，配合CPI判斷通脹趨勢持續性。",
            official= "BLS",
        ))

    # ── TSLA Deliveries ── first business day of Jan/Apr/Jul/Oct
    if month in (1, 4, 7, 10):
        first_bd = _date(year, month, 1)
        while first_bd.weekday() >= 5 or _is_us_holiday(first_bd):
            first_bd += _td(days=1)
        quarter = {1:"Q4", 4:"Q1", 7:"Q2", 10:"Q3"}[month]
        prev_year = year - 1 if month == 1 else year
        events.append(dict(
            date    = first_bd,
            text    = f"TSLA {quarter} {prev_year if month==1 else year}交付數據",
            et_time = "06:00",
            color   = "green",
            impact  = "high",
            note    = f"Tesla季度交付報告，預計{first_bd.strftime('%-m月%-d日')}約06:00-07:00 ET發布。高於/低於華爾街共識直接決定當日TSLA方向，典型Binary Event，注意缺口風險。",
            official= "Tesla IR",
        ))

    # ── Michigan Consumer Sentiment ── last Friday of month (preliminary)
    last_fri = None
    for day in range(_calendar.monthrange(year, month)[1], 0, -1):
        d = _date(year, month, day)
        if d.weekday() == 4:
            last_fri = d
            break
    if last_fri:
        adj_date, _, _ = _adjust_for_holiday(last_fri)
        events.append(dict(
            date    = adj_date,
            text    = "密歇根大學消費者信心（初值）",
            et_time = "10:00",
            color   = "amber",
            impact  = "med",
            note    = "消費者通脹預期分項尤其關鍵，直接影響Fed路徑預期。",
            official= "U of Michigan",
        ))

    return events


def get_week_economic_events(week_monday) -> list[dict]:
    """
    Get all hardcoded economic events for the week of week_monday.
    Returns events where date falls in Mon-Fri of that week.
    """
    from datetime import timedelta as _td
    week_end = week_monday + _td(days=4)

    # Check current month + adjacent months for events that fall in this week
    months_to_check = set()
    months_to_check.add((week_monday.year, week_monday.month))
    months_to_check.add((week_end.year,    week_end.month))

    all_events = []
    for yr, mo in months_to_check:
        all_events.extend(get_economic_calendar(yr, mo))

    # Filter to this week
    week_events = [e for e in all_events
                   if week_monday <= e["date"] <= week_end]
    return week_events


def _long_weekend_warning(week_monday) -> str | None:
    """
    Detect if any day this week is a holiday/long-weekend situation.
    Returns warning string or None.
    """
    from datetime import timedelta as _td
    warnings = []
    for i in range(5):
        d = week_monday + _td(days=i)
        h = _is_us_holiday(d)
        if h:
            warnings.append(f"⚠️ {d.strftime('%-m/%-d')}（{'一二三四五六日'[d.weekday()]}）{h}美股休市")
        # Check if next day is holiday (long weekend)
        nd = d + _td(days=1)
        if _is_us_holiday(nd) and d.weekday() < 4:
            warnings.append(f"⚠️ {d.strftime('%-m/%-d')} 長週末前最後交易日（明日{h or _is_us_holiday(nd)}休市）")
    return " &nbsp;·&nbsp; ".join(warnings) if warnings else None


# ── Known ET release times — auto-fills missing et_time from Groq ────────────
# Keyed by keyword fragments (lowercase). Checked against event text.
KNOWN_ET_TIMES = {
    # Economic data — fixed BLS/BEA/Fed schedule
    "cpi":                    "08:30",
    "消費者物價":              "08:30",
    "ppi":                    "08:30",
    "生產者物價":              "08:30",
    "零售銷售":                "08:30",
    "retail sales":           "08:30",
    "初領失業":                "08:30",
    "jobless claims":         "08:30",
    "非農":                   "08:30",
    "nonfarm payroll":        "08:30",
    "失業率":                  "08:30",
    "gdp":                    "08:30",
    "個人消費支出":            "08:30",
    "pce":                    "08:30",
    "耐用品":                  "08:30",
    "貿易差額":                "08:30",
    "密歇根":                  "10:00",
    "消費者信心":               "10:00",
    "consumer confidence":    "10:00",
    "ism製造":                 "10:00",
    "ism服務":                 "10:00",
    "採購經理":                 "10:00",
    "新屋銷售":                "10:00",
    "成屋銷售":                "10:00",
    "fomc":                   "14:00",
    "聯儲會議":                "14:00",
    "利率決議":                "14:00",
    "鮑威爾記者":              "14:30",
    "沃什記者":                "14:30",
    "warsh press":            "14:30",
    "baker hughes":           "13:00",
    "鑽井數":                  "13:00",
    # Market open/close
    "ipo":                    "09:30",
    "上市":                    "09:30",
    "期權到期":                "16:00",
    "options expiry":         "16:00",
    # TSLA specific
    "tsla交付":               "06:00",   # delivery report ~6am ET on first biz day
    "tsla delivery":          "06:00",
    "q2交付":                  "06:00",
    "q2 delivery":            "06:00",
    "財報":                    "盤後",    # earnings usually after close
    "earnings":               "盤後",
    "業績":                    "盤後",
}

def _fill_et_time(event: dict) -> dict:
    """Auto-fill et_time if empty, based on KNOWN_ET_TIMES keyword match."""
    if event.get("et_time"):
        return event
    text_lower = event.get("text","").lower()
    for keyword, t in KNOWN_ET_TIMES.items():
        if keyword in text_lower:
            event = dict(event, et_time=t)
            break
    return event


def _enrich_fallback(events: list) -> list:
    """Apply _fill_et_time and sort to fallback events list."""
    enriched = []
    for day in events:
        evs = [_fill_et_time(dict(e)) for e in day.get("events",[])]
        evs.sort(key=lambda e: e.get("et_time","") or "99:99")
        enriched.append(dict(day, events=evs))
    return enriched


_FALLBACK_EVENTS = [
    {"date":"2026-06-09","weekday":"周一 MON","events":[
        {"text":"Kevin Warsh 就任美聯儲主席","color":"red","impact":"high","note":"Warsh 鷹派傾向，加息預期上移","et_time":""},
        {"text":"美中貿易談判磋商","color":"amber","impact":"high","note":"90天關稅暫緩窗口期","et_time":""},
    ]},
    {"date":"2026-06-10","weekday":"周二 TUE","events":[
        {"text":"5月 CPI 數據","color":"red","impact":"high","note":"YoY 3.8%；偏熱→沽科技","et_time":"08:30"},
    ]},
    {"date":"2026-06-11","weekday":"周三 WED","events":[
        {"text":"5月 PPI 數據","color":"amber","impact":"high","note":"配合CPI判斷通脹方向","et_time":"08:30"},
        {"text":"伊朗/霍爾木茲局勢","color":"red","impact":"high","note":"和平協議談判中，影響油價","et_time":""},
    ]},
    {"date":"2026-06-12","weekday":"周四 THU","events":[
        {"text":"SpaceX (SPCX) Nasdaq IPO","color":"green","impact":"high","note":"$135/股，$1.77T估值","et_time":"09:30"},
        {"text":"密歇根大學消費者信心","color":"amber","impact":"med","note":"通脹預期數據影響Fed路徑","et_time":"10:00"},
        {"text":"Baker Hughes 鑽井數","color":"blue","impact":"low","note":"油市供應端參考","et_time":"13:00"},
    ]},
    {"date":"2026-06-13","weekday":"周五 FRI","events":[
        {"text":"FOMC 靜默期（下週一三）","color":"purple","impact":"high","note":"Warsh 首次FOMC 6/16-17","et_time":""},
        {"text":"美伊和平協議後續","color":"red","impact":"high","note":"若簽署→週一油價急跌","et_time":""},
    ]},
]

_WEEKDAY_MAP = ["周一 MON","周二 TUE","周三 WED","周四 THU","周五 FRI","周六 SAT","周日 SUN"]

def _merge_hardcoded(events: list, week_monday) -> list:
    """
    Merge hardcoded get_week_economic_events() into AI-generated events list.
    Hardcoded events take priority — if same date+keyword exists, update et_time/note.
    New hardcoded events are appended and sorted.
    """
    from datetime import date as _date
    hc_events = get_week_economic_events(week_monday)
    if not hc_events: return events

    # Build a lookup of existing event texts per date (lowercased for matching)
    date_idx = {day["date"]: day for day in events}

    for hc in hc_events:
        date_str = hc["date"].isoformat()
        hc_text_low = hc["text"].lower()

        if date_str in date_idx:
            day = date_idx[date_str]
            # Check if a similar event already exists (keyword match)
            matched = False
            for existing in day["events"]:
                ex_low = existing.get("text","").lower()
                # Match by shared key terms
                key_terms = [w for w in hc_text_low.split() if len(w) > 2]
                if any(term in ex_low for term in key_terms[:3]):
                    # Update et_time if missing/wrong, keep AI note if longer
                    if not existing.get("et_time"):
                        existing["et_time"] = hc["et_time"]
                    if len(hc.get("note","")) > len(existing.get("note","")):
                        existing["note"] = hc["note"]
                    existing["official"] = hc.get("official","")
                    matched = True
                    break
            if not matched:
                # Add as new event with official badge
                new_ev = dict(hc)
                new_ev.pop("date", None)
                new_ev["text"] = f"[官方] {hc['text']}"
                day["events"].append(new_ev)
                # Re-sort
                day["events"].sort(key=lambda e: e.get("et_time","") or "99:99")
        else:
            # Date not in AI calendar at all — add new day entry
            weekday_idx = hc["date"].weekday()
            wday_map = ["周一 MON","周二 TUE","周三 WED","周四 THU","周五 FRI"]
            if weekday_idx < 5:
                new_ev = dict(hc); new_ev.pop("date", None)
                new_ev["text"] = f"[官方] {hc['text']}"
                events.append({
                    "date":    date_str,
                    "weekday": wday_map[weekday_idx],
                    "events":  [new_ev],
                })
                events.sort(key=lambda d: d["date"])

    # Apply long-weekend warning to any day this week
    lw_warn = _long_weekend_warning(week_monday)
    if lw_warn:
        today_str = datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")
        for day in events:
            if day["date"] == today_str:
                # Add as a meta-note at top of today's events
                warn_ev = dict(
                    text    = f"長週末/假期提醒：{lw_warn}",
                    et_time = "",
                    color   = "amber",
                    impact  = "high",
                    note    = "長週末前流動性下降，期權時間值衰減加速，注意隔週Gap風險",
                    official= "",
                )
                # Only add if not already present
                if not any("長週末" in e.get("text","") for e in day["events"]):
                    day["events"].insert(0, warn_ev)
                break
    return events


def fetch_weekly_events(serper_key: str, groq_key: str) -> list:
    monday = week_monday_str()
    if st.session_state.weekly_events and st.session_state.weekly_events_fetched == monday:
        return st.session_state.weekly_events
    if not serper_key or not groq_key:
        return _enrich_fallback(_FALLBACK_EVENTS)
    queries = [
        "US economic calendar CPI PPI retail sales this week",
        "Federal Reserve Fed chair Warsh Powell FOMC this week",
        "Trump China Xi trade tariff meeting this week",
        "Iran war ceasefire oil price this week",
        "Trump executive order market impact this week",
    ]
    snippets = []
    for q in queries:
        try:
            r = requests.post("https://google.serper.dev/news",
                headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                json={"q": q, "num": 4, "hl": "en", "gl": "us"}, timeout=8)
            for item in r.json().get("news", []):
                snippets.append(f"[{item.get('date','')}] {item.get('title','')} — {item.get('snippet','')}")
        except Exception:
            pass
    if not snippets:
        return _enrich_fallback(_FALLBACK_EVENTS)
    et = pytz.timezone("America/New_York")
    today = datetime.now(et).date()
    mon   = today - timedelta(days=today.weekday())
    dates = [(mon + timedelta(days=i)).isoformat() for i in range(5)]
    wdays = [_WEEKDAY_MAP[i] for i in range(5)]
    prompt = f"""你是美股宏觀分析師。根據以下本週新聞，為交易員生成一個五天事件日曆。

新聞（最多30條）：
{chr(10).join(snippets[:30])}

本週日期：
{', '.join(f"{d}({w})" for d,w in zip(dates,wdays))}

輸出 **純 JSON**，格式如下（不要任何其他文字或 markdown）：
[
  {{
    "date": "YYYY-MM-DD",
    "weekday": "周X XXX",
    "events": [
      {{
        "text": "事件名稱（繁體中文，不含時間）",
        "et_time": "HH:MM 或空字串",
        "color": "red|amber|blue|purple|green",
        "impact": "high|med|low",
        "note": "一句話市場影響分析（繁體中文）"
      }}
    ]
  }}
]

規則：
- 每天 1-4 個事件，只列重要事件，按 ET 時間升序排列
- et_time: **必須填寫**已知時間，不可留空字串。參考以下固定時間表：
  * 08:30 ET — CPI/PPI/零售銷售/非農/初領失業金/PCE/耐用品
  * 10:00 ET — 密歇根消費者信心/ISM/新屋成屋銷售/消費者信心
  * 13:00 ET — Baker Hughes鑽井數
  * 14:00 ET — FOMC利率決議
  * 14:30 ET — Fed主席記者會
  * 09:30 ET — IPO首日上市/市場開盤事件
  * 盤後 — 財報/業績發布（若無具體時間填"盤後"）
  * 06:00 ET — TSLA交付數據（季度初第一個工作日）
  * 無法確認時間的事件填空字串
- color: red=重大風險/央行/地緣, amber=中等/貿易/數據, blue=例行數據, purple=聯儲官員, green=利好
- impact: high=市場必看, med=中等影響, low=參考
- note 要具體，點出對科技股/TSLA 的影響方向
- **特別注意**：若本週或下週初有TSLA Q2交付數據（通常7月第一個工作日）、TSLA財報（通常7月第三週）、FOMC會議，必須列入並標注準確時間"""
    try:
        raw = groq_chat(prompt, groq_key, max_tokens=1600, temperature=0.2)
        raw = raw.replace("```json","").replace("```","").strip()
        events = json.loads(raw)
        for day in events:
            assert "date" in day and "events" in day
            # Auto-fill missing et_time from KNOWN_ET_TIMES
            day["events"] = [_fill_et_time(e) for e in day["events"]]
            # Sort events by ET time ascending
            day["events"].sort(key=lambda e: e.get("et_time","") or "99:99")
        # Merge hardcoded economic events on top of Groq output
        events = _merge_hardcoded(events, week_monday=mon)
        st.session_state.weekly_events = events
        st.session_state.weekly_events_fetched = monday
        return events
    except Exception:
        fb = _enrich_fallback(_FALLBACK_EVENTS)
        return _merge_hardcoded(fb, week_monday=datetime.now(pytz.timezone("America/New_York")).date() - timedelta(days=datetime.now(pytz.timezone("America/New_York")).date().weekday()))


def render_weekly_calendar(events: list, source_label: str):
    et = pytz.timezone("America/New_York")
    today_str = datetime.now(et).strftime("%Y-%m-%d")
    # Long-weekend/holiday banner (from _merge_hardcoded)
    et_now_cal  = datetime.now(pytz.timezone("America/New_York"))
    _wk_monday  = (et_now_cal.date() - timedelta(days=et_now_cal.date().weekday()))
    _lw_warn    = _long_weekend_warning(_wk_monday)
    if _lw_warn:
        st.markdown(
            f'<div style="background:#FFF8E8;border-left:3px solid #D4A017;'
            f'border-radius:0 4px 4px 0;padding:.45rem .85rem;'
            f'font-family:var(--sans,sans-serif);font-size:.76rem;color:#6B5000;'
            f'margin-bottom:.4rem">📅 {_lw_warn}</div>',
            unsafe_allow_html=True)

    for day in events:
        if day["date"] == today_str:
            high = [e for e in day.get("events",[]) if e.get("impact") == "high"]
            if high:
                alerts = " &nbsp;|&nbsp; ".join([f"⚠️ <b>{_html.escape(e['text'])}</b>" for e in high])
                st.markdown(f'<div class="cal-alert-strip">🔔 今日高影響事件：{alerts}</div>',
                            unsafe_allow_html=True)
            break

    # ── TSLA Upcoming Key Events reminder (hardcoded awareness) ──
    et_now   = datetime.now(pytz.timezone("America/New_York"))
    et_today = et_now.date()
    reminders = []
    # Q2 delivery: first business day of July
    import calendar as _cal
    _jul1 = et_today.replace(month=7, day=1)
    # Find first Mon-Fri of July
    _q2_delivery = _jul1
    while _q2_delivery.weekday() >= 5:   # skip Sat/Sun
        _q2_delivery += timedelta(days=1)
    days_to_delivery = (_q2_delivery - et_today).days
    if 0 <= days_to_delivery <= 7:
        _d_str = _q2_delivery.strftime("%-m月%-d日")
        _urgency = "🚨 今日" if days_to_delivery == 0 else f"📅 {days_to_delivery}日後"
        reminders.append(
            f"{_urgency} TSLA Q2交付數據預計 <b>{_d_str} ~06:00 ET</b> 發布 — "
            f"高於預期→缺口上升，低於預期→缺口下跌，Binary Event！"
        )
    # Q2 earnings: typically 3rd Tuesday/Wednesday of July
    _q2_earn_approx = et_today.replace(month=7, day=22)
    days_to_earn = (_q2_earn_approx - et_today).days
    if 0 <= days_to_earn <= 14:
        reminders.append(
            f"📅 {days_to_earn}日後 TSLA Q2財報預計 <b>7月22日前後 盤後</b> — "
            f"提前留意IV急升，考慮earnings play策略"
        )
    if reminders:
        for r in reminders:
            st.markdown(
                f'<div style="background:#EAF4EE;border-left:3px solid #3A7D5C;'
                f'border-radius:0 4px 4px 0;padding:.45rem .85rem;font-family:var(--sans,sans-serif);'
                f'font-size:.76rem;color:#1E4D35;margin-bottom:.3rem">🚗 {r}</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-label">▸ 📅 本週重磅事件日曆 · 宏觀催化劑追蹤</div>', unsafe_allow_html=True)
    imp_map  = {"high":"imp-high","med":"imp-med","low":"imp-low"}
    imp_text = {"high":"高影響","med":"中影響","low":"低影響"}
    if events:
        d0 = datetime.strptime(events[0]["date"],"%Y-%m-%d")
        d4 = datetime.strptime(events[-1]["date"],"%Y-%m-%d")
        cal_title = f"📅 {d0.strftime('%b %-d')}–{d4.strftime('%-d, %Y')} &nbsp;· 重磅事件週"
    else:
        cal_title = "📅 本週事件"
    cal_html = f'<div class="cal-wrap"><div class="cal-title">{cal_title}</div><div class="cal-grid">'
    for day in events:
        is_today = day["date"] == today_str
        is_past  = day["date"] < today_str
        day_cls  = "cal-day today" if is_today else ("cal-day past" if is_past else "cal-day")
        date_obj  = datetime.strptime(day["date"],"%Y-%m-%d")
        date_disp = date_obj.strftime("%-d")
        today_badge = '<span class="cal-today-badge">TODAY</span>' if is_today else ""
        evs_html = ""
        for ev in day.get("events",[]):
            dot      = ev.get("color","blue")
            ic       = imp_map.get(ev.get("impact","low"),"imp-low")
            il       = imp_text.get(ev.get("impact","low"),"")
            text     = _html.escape(ev.get("text",""))
            note     = _html.escape(ev.get("note",""))
            et_t     = ev.get("et_time","")
            official = ev.get("official","")
            if et_t and et_t != "盤後":
                time_tag = ('<span style="font-family:var(--mono,monospace);font-size:.54rem;'
                            'color:var(--muted,#8A8278);margin-right:.2rem">' + et_t + ' ET</span>')
            elif et_t == "盤後":
                time_tag = ('<span style="font-family:var(--mono,monospace);font-size:.54rem;'
                            'color:var(--muted,#8A8278);margin-right:.2rem">盤後</span>')
            else:
                time_tag = ""
            official_tag = (
                '<span style="font-family:var(--mono,monospace);font-size:.5rem;'
                'background:var(--up-bg,#EAF4EE);color:var(--up,#3A7D5C);'
                'padding:.02rem .28rem;border-radius:2px;margin-left:.25rem">' +
                _html.escape(official) + '</span>'
            ) if official else ""
            evs_html += (
                '<div class="cal-event" title="' + note + '">' +
                '<div class="cal-dot ' + dot + '"></div>' +
                '<div><span class="cal-impact ' + ic + '">' + il + '</span> ' +
                time_tag + text + official_tag +
                '</div></div>'
            )
        cal_html += f"""
        <div class="{day_cls}">
          <div class="cal-dayname">{day['weekday']}</div>
          <div class="cal-date">{date_disp}{today_badge}</div>
          {evs_html}
        </div>"""
    cal_html += f'</div><div class="cal-source">{source_label}</div></div>'
    st.markdown(cal_html, unsafe_allow_html=True)
    with st.expander("📋 詳細事件影響分析", expanded=False):
        for day in events:
            is_today = day["date"] == today_str
            prefix = "🔴 今日 · " if is_today else ""
            for ev in day.get("events",[]):
                if ev.get("impact") == "high":
                    et_t = ev.get("et_time","")
                    time_str = f" ({et_t} ET)" if et_t else ""
                    st.markdown(f"**{prefix}{day['weekday']} — {ev['text']}{time_str}**\n> {ev.get('note','')}\n")


# ── Oil panel ─────────────────────────────────────────────────────────────────
OIL_TICKERS = {
    "CL=F": {"label":"WTI 原油","unit":"美元/桶"},
    "BZ=F": {"label":"Brent 原油","unit":"美元/桶"},
    "NG=F": {"label":"天然氣","unit":"美元/MMBtu"},
}


# ── US Treasury Yields ────────────────────────────────────────────────────────
YIELD_TICKERS = {
    "^IRX": {"label":"3M","full":"3月期","threshold":None},
    "^FVX": {"label":"5Y","full":"5年","threshold":None},
    "^TNX": {"label":"10Y","full":"10年","threshold":4.5},
    "^TYX": {"label":"30Y","full":"30年","threshold":5.0},
}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_yields() -> dict:
    """Fetch US Treasury yield data. Yields are quoted as % (e.g. 4.25 = 4.25%)."""
    results = {}
    for ticker, meta in YIELD_TICKERS.items():
        d = None
        try: d = _yahoo_chart_api(ticker)
        except Exception: pass
        if d is None or d.get("error") or not d.get("price"):
            try:
                df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    price = float(df["Close"].iloc[-1])
                    prev  = float(df["Close"].iloc[-2]) if len(df) >= 2 else price
                    d = dict(price=price, prev=prev,
                             reg_chg=price-prev, reg_pct=(price-prev)/prev*100 if prev else None,
                             error=None)
            except Exception: pass
        if d and not d.get("error") and d.get("price"):
            price = d["price"]
            prev  = d.get("prev") or price
            chg   = d.get("reg_chg") or (price - prev)
            # Yields: change in basis points = chg * 100
            bp    = round(chg * 100, 1)
            results[ticker] = dict(
                label    = meta["label"],
                full     = meta["full"],
                threshold= meta["threshold"],
                value    = price,      # e.g. 4.25 (%)
                prev     = prev,
                chg      = chg,        # e.g. +0.05
                bp       = bp,         # basis points change
            )
        else:
            results[ticker] = dict(label=meta["label"], full=meta["full"],
                                   threshold=meta["threshold"], error="—")
    return results


def _yield_signal(y10, y2_or_3m, y30) -> tuple[str, str, str]:
    """
    Interpret yield curve shape → (signal_text, bg_color, border_color)
    Uses 10Y as primary; 3M as short-end proxy when 2Y unavailable.
    """
    if y10 is None: return "殖利率數據不足", "#F0EDE8", "#D8D0C0"
    # Absolute level signals
    if y10 >= 5.0:
        return "⚠️ 10年息 ≥5.0% — 股市估值嚴重受壓，成長股高風險", "#FDECEA", "#C0392B"
    if y10 >= 4.5:
        return "🔶 10年息 ≥4.5% — 科技股/TSLA承壓，留意Fed路徑", "#FFF8E8", "#D4A017"
    if y10 <= 3.5:
        return "✅ 10年息 ≤3.5% — 估值壓力低，利好成長股", "#EAF4EE", "#3A7D5C"
    # Inversion signal
    if y2_or_3m is not None and y2_or_3m > y10 + 0.1:
        return f"🔴 殖利率曲線倒掛 ({y2_or_3m:.2f}% > {y10:.2f}%) — 衰退預警訊號", "#FDECEA", "#C0392B"
    return f"10年息 {y10:.2f}% — 中性水平，暫無極端壓力", "#F0EDE8", "#D8D0C0"


def render_yield_panel():
    st.markdown('<div class="section-label">▸ 🏦 美債殖利率監控</div>', unsafe_allow_html=True)
    yields = fetch_yields()

    # Grid of 4 yield cards
    html = '<div class="yield-grid">'
    for ticker, d in yields.items():
        if d.get("error"):
            html += (f'<div class="yield-card"><div class="yield-label">{d["label"]}</div>'
                     f'<div class="yield-value flat">—</div></div>')
            continue
        val  = d["value"]
        bp   = d["bp"]
        chg_col = "up" if bp > 0 else ("down" if bp < 0 else "flat")
        bp_str  = (f'+{bp:.1f}' if bp >= 0 else f'{bp:.1f}') + "bp"
        # Threshold warning badge
        badge = ""
        thr = d.get("threshold")
        if thr and val >= thr:
            badge = f'<span class="signal-badge signal-bearish">≥{thr}%</span>'
        elif thr and val >= thr - 0.2:
            badge = f'<span class="signal-badge signal-neutral">接近{thr}%</span>'
        html += (
            f'<div class="yield-card">' +
            f'<div class="yield-label">{d["label"]} {d["full"]}{badge}</div>' +
            f'<div class="yield-value {chg_col}">{val:.3f}%</div>' +
            f'<div class="yield-chg {chg_col}">{bp_str} vs昨</div>' +
            f'</div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

    # Yield curve signal bar
    y10  = yields.get("^TNX",{}).get("value")
    y3m  = yields.get("^IRX",{}).get("value")
    y30  = yields.get("^TYX",{}).get("value")
    msg, bg, bc = _yield_signal(y10, y3m, y30)

    # Spread display
    spread_html = ""
    if y10 and y3m:
        spread = y10 - y3m
        s_col  = "var(--up)" if spread > 0 else "var(--down)"
        spread_html = (
            f'<span style="font-family:var(--mono,monospace);font-size:.68rem;'
            f'color:{s_col};margin-left:1rem">'
            f'10Y-3M 利差: {"+":s}{spread:+.2f}%</span>'
        ).replace("{"+":s}","")
        spread_html = (
            f'<span style="font-family:var(--mono,monospace);font-size:.68rem;'
            f'color:{s_col};margin-left:1rem">'
            f'10Y-3M 利差: {spread:+.2f}%</span>'
        )
    st.markdown(
        f'<div class="yield-signal" style="background:{bg};border-left-color:{bc};border-left-width:3px">'
        f'{msg}{spread_html}</div>',
        unsafe_allow_html=True)


# ── Sector Rotation ───────────────────────────────────────────────────────────
SECTORS = [
    ("XLK",  "科技",   "Technology"),
    ("XLF",  "金融",   "Financials"),
    ("XLE",  "能源",   "Energy"),
    ("XLV",  "醫療",   "Healthcare"),
    ("XLI",  "工業",   "Industrials"),
    ("XLC",  "通訊",   "Comm Svcs"),
    ("XLY",  "非必需", "Cons Discr"),
    ("XLU",  "公用",   "Utilities"),
]

@st.cache_data(ttl=60, show_spinner=False)
def fetch_sectors() -> list:
    """Fetch all sector ETFs and return sorted by today's performance."""
    results = []
    for ticker, name_zh, name_en in SECTORS:
        d = None
        try: d = _yahoo_chart_api(ticker)
        except Exception: pass
        if d is None or d.get("error") or not d.get("price"):
            try:
                df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    price = float(df["Close"].iloc[-1])
                    prev  = float(df["Close"].iloc[-2]) if len(df) >= 2 else price
                    d = dict(price=price, prev=prev,
                             pre_price=None, pre_pct=None, reg_pct=(price-prev)/prev*100 if prev else 0,
                             error=None)
            except Exception: pass
        if d and not d.get("error"):
            # Choose best available pct
            et_t = datetime.now(pytz.timezone("America/New_York")).time()
            _is_reg = time(9,30) <= et_t < time(16,0)
            if d.get("pre_pct") is not None and not _is_reg:
                pct = d["pre_pct"]
            elif d.get("reg_pct") is not None:
                pct = d["reg_pct"]
            else:
                pct = 0.0
            results.append(dict(
                ticker   = ticker,
                name_zh  = name_zh,
                name_en  = name_en,
                price    = d.get("price") or d.get("pre_price"),
                pct      = pct or 0.0,
                error    = None,
            ))
        else:
            results.append(dict(ticker=ticker, name_zh=name_zh, name_en=name_en,
                                price=None, pct=None, error=True))
    # Sort descending by pct (leader → laggard)
    results.sort(key=lambda x: x["pct"] if x["pct"] is not None else -999, reverse=True)
    return results


def _rotation_insight(sectors: list) -> str:
    """Generate a one-line rotation insight from sector rankings."""
    valid = [s for s in sectors if not s.get("error") and s["pct"] is not None]
    if len(valid) < 3: return ""
    leader  = valid[0]
    laggard = valid[-1]
    tech    = next((s for s in valid if s["ticker"] == "XLK"), None)
    energy  = next((s for s in valid if s["ticker"] == "XLE"), None)
    util    = next((s for s in valid if s["ticker"] == "XLU"), None)

    parts = []
    # Risk-on / Risk-off判斷
    if leader["ticker"] in ("XLK","XLY","XLC"):
        parts.append("📈 <b>Risk-On</b>：科技/消費領漲，市場情緒偏進取")
    elif leader["ticker"] in ("XLU","XLV"):
        parts.append("🛡️ <b>Risk-Off</b>：防禦板塊領漲，資金避險情緒上升")
    elif leader["ticker"] == "XLE":
        parts.append("🛢️ <b>能源主導</b>：油價驅動，留意通脹預期上升")
    elif leader["ticker"] == "XLF":
        parts.append("🏦 <b>金融領漲</b>：利率預期上升或曲線走陡")

    # TSLA-specific
    if tech:
        if tech["pct"] > 0.5:
            parts.append(f"XLK 科技 {fmt_pct(tech['pct'])} 利好 TSLA")
        elif tech["pct"] < -0.5:
            parts.append(f"XLK 科技 {fmt_pct(tech['pct'])} 壓制 TSLA")

    # Laggard warning
    if laggard["pct"] is not None and laggard["pct"] < -1.5:
        parts.append(f"⚠️ {laggard['name_zh']}({laggard['ticker']}) 大幅落後 {fmt_pct(laggard['pct'])}")

    return " &nbsp;·&nbsp; ".join(parts) if parts else f"領漲：{leader['name_zh']} · 落後：{laggard['name_zh']}"


def render_sector_panel():
    st.markdown('<div class="section-label">▸ 🔄 板塊輪動監控</div>', unsafe_allow_html=True)
    with st.spinner("載入板塊數據..."):
        sectors = fetch_sectors()

    valid = [s for s in sectors if not s.get("error") and s["pct"] is not None]
    max_abs = max((abs(s["pct"]) for s in valid), default=1) or 1

    html = '<div class="sector-grid">'
    for i, s in enumerate(sectors):
        if s.get("error") or s["pct"] is None:
            html += (f'<div class="sector-card"><div class="sector-name">{s["name_zh"]}</div>'
                     f'<div class="sector-etf">{s["ticker"]}</div>'
                     f'<div class="sector-pct flat">—</div></div>')
            continue
        pct  = s["pct"]
        col  = "var(--up)" if pct > 0 else "var(--down)"
        col_cls = "up" if pct > 0 else ("down" if pct < 0 else "flat")
        bar_w = min(abs(pct) / max_abs * 100, 100)
        # leader/laggard border
        extra_cls = ""
        if i == 0: extra_cls = " sector-leader"
        elif i == len(sectors)-1: extra_cls = " sector-laggard"
        rank_sym = "▲" if i == 0 else ("▼" if i == len(sectors)-1 else f"#{i+1}")
        html += (
            f'<div class="sector-card{extra_cls}">' +
            f'<div class="sector-rank">{rank_sym}</div>' +
            f'<div class="sector-name">{s["name_zh"]}</div>' +
            f'<div class="sector-etf">{s["ticker"]}</div>' +
            f'<div class="sector-pct {col_cls}">{fmt_pct(pct)}</div>' +
            f'<div class="sector-bar" style="width:{bar_w:.0f}%;background:{col}"></div>' +
            f'</div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

    # Rotation insight
    insight = _rotation_insight(sectors)
    if insight:
        st.markdown(
            f'<div class="rotation-insight">{insight}</div>',
            unsafe_allow_html=True)

@st.cache_data(ttl=60, show_spinner=False)
def fetch_oil_data() -> dict:
    results = {}
    for ticker, meta in OIL_TICKERS.items():
        d = None
        try: d = _yahoo_chart_api(ticker)
        except Exception: pass
        if d is None or d.get("error") or not d.get("price"):
            try:
                df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    price = float(df["Close"].iloc[-1]); prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else price
                    chg = price - prev; pct = chg/prev*100 if prev else None
                    d = dict(price=price, prev=prev, reg_chg=chg, reg_pct=pct,
                             high=float(df["High"].iloc[-1]) if "High" in df.columns else None,
                             low=float(df["Low"].iloc[-1])  if "Low"  in df.columns else None,
                             error=None)
            except Exception: pass
        if d is None or d.get("error") or not d.get("price"):
            try:
                info = yf.Ticker(ticker).info
                price = info.get("regularMarketPrice") or info.get("previousClose")
                prev  = info.get("previousClose") or info.get("regularMarketPreviousClose")
                if price:
                    chg = (price-prev) if (price and prev) else None
                    pct = (chg/prev*100) if (chg and prev) else None
                    d = dict(price=price, prev=prev, reg_chg=chg, reg_pct=pct,
                             high=info.get("dayHigh"), low=info.get("dayLow"), error=None)
            except Exception as e: d = dict(error=str(e))
        if d and not d.get("error") and d.get("price"):
            price = d["price"]; prev = d.get("prev")
            chg = d.get("reg_chg") or ((price-prev) if (price and prev) else None)
            pct = d.get("reg_pct") or ((chg/prev*100) if (chg and prev) else None)
            results[ticker] = dict(label=meta["label"], unit=meta["unit"],
                                   price=price, chg=chg, pct=pct,
                                   high=d.get("high"), low=d.get("low"))
        else:
            results[ticker] = dict(label=meta["label"], unit=meta["unit"],
                                   error=d.get("error","fetch failed") if d else "fetch failed")
    return results

def _oil_direction_label(pct) -> str:
    if pct is None: return "變動"
    if pct >  2:    return "急升"
    if pct >  0.5:  return "上漲"
    if pct < -2:    return "急跌"
    if pct < -0.5:  return "下跌"
    return "平穩"

def render_oil_panel():
    st.markdown('<div class="section-label">▸ 🛢️ 能源價格監控</div>', unsafe_allow_html=True)
    oil  = fetch_oil_data()
    cols = st.columns(3)
    for i, (ticker, d) in enumerate(oil.items()):
        with cols[i]:
            if d.get("error"):
                st.markdown(f'<div class="oil-card"><div class="oil-label">{d["label"]}</div>'
                            f'<div class="oil-price flat">—</div>'
                            f'<div style="font-size:.6rem;color:var(--muted,#8A8278)">{d["error"][:40]}</div>'
                            f'</div>', unsafe_allow_html=True)
                continue
            pct, chg = d.get("pct"), d.get("chg")
            col = "up" if (pct and pct>0) else ("down" if (pct and pct<0) else "flat")
            sign = "+" if (chg or 0) >= 0 else ""
            alert = ""
            if ticker in ("CL=F","BZ=F") and d.get("price"):
                p = d["price"]
                if   p > 100: alert = '<span class="signal-badge signal-bearish">高風險</span>'
                elif p > 90:  alert = '<span class="signal-badge signal-neutral">留意</span>'
                elif p < 80:  alert = '<span class="signal-badge signal-bullish">溫和</span>'
            st.markdown(f'<div class="oil-card">'
                        f'<div class="oil-label">{d["label"]} {alert}</div>'
                        f'<div class="oil-price {col}">${fmt_num(d.get("price"))}</div>'
                        f'<div class="oil-chg {col}">{sign}{fmt_num(chg)} ({fmt_pct(pct)})</div>'
                        f'<div class="oil-meta">高 {fmt_num(d.get("high"))} · 低 {fmt_num(d.get("low"))} · {d["unit"]}</div>'
                        f'</div>', unsafe_allow_html=True)
    wti = oil.get("CL=F",{})
    p, pct = wti.get("price"), wti.get("pct")
    if p and pct is not None:
        if   pct >  2:   msg,bg,bc,tc = f"⚠️ WTI 急升 <b>{fmt_pct(pct)}</b>，科技股承壓，注意通脹預期上移","#FDECEA","#C0392B","#7B1A12"
        elif pct >  0.5: msg,bg,bc,tc = f"🔶 WTI 上漲 <b>{fmt_pct(pct)}</b>，留意 TSLA/科技股壓力","#FFF8E8","#D4A017","#6B5000"
        elif pct < -2:   msg,bg,bc,tc = f"✅ WTI 急跌 <b>{fmt_pct(pct)}</b>，通脹壓力減輕，利好科技/成長股","#EAF4EE","#3A7D5C","#1E4D35"
        elif pct < -0.5: msg,bg,bc,tc = f"🔽 WTI 下跌 <b>{fmt_pct(pct)}</b>，能源成本回落，科技股溫和利好","#EAF4EE","#3A7D5C","#1E4D35"
        else:            msg,bg,bc,tc = f"WTI 平穩 <b>{fmt_pct(pct)}</b>，能源因素對市場影響中性","#F0EDE8","#D8D0C0","#8A8278"
        st.markdown(f'<div style="background:{bg};border-left:3px solid {bc};border-radius:0 4px 4px 0;'
                    f'padding:.5rem .85rem;font-size:.76rem;color:{tc};margin-top:.45rem">{msg}</div>',
                    unsafe_allow_html=True)



# ── TSLA Technical Analysis Panel ─────────────────────────────────────────────
import hashlib as _hashlib

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, pc = df["High"], df["Low"], df["Close"].shift(1)
    tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))

def _macd(series: pd.Series):
    fast = _ema(series, 12); slow = _ema(series, 26)
    macd_line = fast - slow; signal = _ema(macd_line, 9)
    return macd_line, signal, macd_line - signal

@st.cache_data(ttl=120, show_spinner=False)
def fetch_tsla_technicals(period: str = "3mo") -> dict:
    """
    Fetch TSLA OHLCV + compute EMA20/50/200, ATR14, RSI14, MACD, key levels.
    Returns dict with all values needed for render_tsla_tech_panel().
    """
    try:
        df = yf.download("TSLA", period=period, interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty: raise ValueError("Empty dataframe")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close","High","Low","Open","Volume"])

        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]

        # EMAs
        ema20  = _ema(close, 20)
        ema50  = _ema(close, 50)
        ema200 = _ema(close, 200)

        # ATR
        atr14  = _atr(df, 14)

        # RSI
        rsi14  = _rsi(close, 14)

        # MACD
        macd_line, macd_sig, macd_hist = _macd(close)

        # Current values
        price    = float(close.iloc[-1])
        prev     = float(close.iloc[-2]) if len(close) >= 2 else price
        atr_val  = float(atr14.iloc[-1])
        rsi_val  = float(rsi14.iloc[-1])
        e20      = float(ema20.iloc[-1])
        e50      = float(ema50.iloc[-1])
        e200     = float(ema200.iloc[-1])
        macd_v   = float(macd_line.iloc[-1])
        macd_s   = float(macd_sig.iloc[-1])
        macd_h   = float(macd_hist.iloc[-1])

        # Key levels: recent highs/lows (20-day swing)
        recent   = df.tail(20)
        r20h     = float(recent["High"].max())
        r20l     = float(recent["Low"].min())
        r5h      = float(df.tail(5)["High"].max())
        r5l      = float(df.tail(5)["Low"].min())

        # Gap detection: today open vs yesterday close
        today_open = float(df["Open"].iloc[-1])
        gap_pct    = (today_open - prev) / prev * 100 if prev else 0

        # ATR-based zones
        atr_stop_long  = price - 1.5 * atr_val   # 1.5x ATR below price
        atr_stop_short = price + 1.5 * atr_val
        atr_target1    = price + 2.0 * atr_val
        atr_target2    = price + 3.5 * atr_val

        # EMA alignment signal
        bull_align = price > e20 > e50       # price above EMA20 > EMA50
        bear_align = price < e20 < e50
        ema200_above = price > e200

        # ATR compression: current ATR vs 20-day avg ATR
        atr_20avg = float(atr14.tail(20).mean())
        atr_ratio = atr_val / atr_20avg if atr_20avg > 0 else 1.0

        # Volume spike
        vol_today  = float(df["Volume"].iloc[-1])
        vol_20avg  = float(df["Volume"].tail(20).mean())
        vol_ratio  = vol_today / vol_20avg if vol_20avg > 0 else 1.0

        return dict(
            price=price, prev=prev, atr=atr_val, rsi=rsi_val,
            e20=e20, e50=e50, e200=e200,
            macd=macd_v, macd_sig=macd_s, macd_hist=macd_h,
            r20h=r20h, r20l=r20l, r5h=r5h, r5l=r5l,
            gap_pct=gap_pct, today_open=today_open,
            atr_stop_long=atr_stop_long, atr_stop_short=atr_stop_short,
            atr_target1=atr_target1, atr_target2=atr_target2,
            bull_align=bull_align, bear_align=bear_align, ema200_above=ema200_above,
            atr_ratio=atr_ratio, vol_ratio=vol_ratio,
            error=None,
        )
    except Exception as e:
        return dict(error=str(e))


def _tech_signal_summary(t: dict, shares: int) -> list[str]:
    """Generate trading signal bullets from technicals dict."""
    lines = []
    price = t["price"]

    # 1. EMA alignment
    if t["bull_align"]:
        lines.append(f"✅ EMA對齊看多：價格({fmt_num(price)}) > EMA20({fmt_num(t['e20'])}) > EMA50({fmt_num(t['e50'])})")
    elif t["bear_align"]:
        lines.append(f"🔴 EMA對齊看空：價格({fmt_num(price)}) < EMA20({fmt_num(t['e20'])}) < EMA50({fmt_num(t['e50'])})")
    else:
        lines.append(f"⚠️ EMA混亂：無明確方向 — E20 {fmt_num(t['e20'])} / E50 {fmt_num(t['e50'])}")

    # 2. RSI
    rsi = t["rsi"]
    if   rsi >= 75: lines.append(f"🔴 RSI {rsi:.1f} — 超買，注意回調風險")
    elif rsi >= 60: lines.append(f"🟡 RSI {rsi:.1f} — 偏強，動能持續但注意高位")
    elif rsi <= 30: lines.append(f"✅ RSI {rsi:.1f} — 超賣，反彈機會")
    elif rsi <= 45: lines.append(f"🟡 RSI {rsi:.1f} — 偏弱，逢高沽壓")
    else:           lines.append(f"◆ RSI {rsi:.1f} — 中性區間")

    # 3. MACD
    if t["macd_hist"] > 0 and t["macd"] > t["macd_sig"]:
        lines.append(f"✅ MACD 金叉 ({t['macd']:.3f} > {t['macd_sig']:.3f}) — 動能看多")
    elif t["macd_hist"] < 0 and t["macd"] < t["macd_sig"]:
        lines.append(f"🔴 MACD 死叉 ({t['macd']:.3f} < {t['macd_sig']:.3f}) — 動能看空")
    else:
        lines.append(f"◆ MACD 收斂中 ({t['macd']:.3f} / {t['macd_sig']:.3f})")

    # 4. ATR compression
    if t["atr_ratio"] < 0.7:
        lines.append(f"⚡ ATR壓縮 ({t['atr_ratio']:.2f}x均值) — 蓄勢待發，注意方向突破")
    elif t["atr_ratio"] > 1.5:
        lines.append(f"🌊 ATR擴張 ({t['atr_ratio']:.2f}x均值) — 高波動，嚴控倉位")

    # 5. Volume
    if t["vol_ratio"] > 2.0:
        lines.append(f"📊 成交量異常 {t['vol_ratio']:.1f}x均量 — 機構參與，方向可信")
    elif t["vol_ratio"] > 1.5:
        lines.append(f"📊 成交量偏高 {t['vol_ratio']:.1f}x均量")

    # 6. ATR trade setup
    atr = t["atr"]
    lines.append(
        f"📐 ATR=${atr:.2f} | "
        f"多單止損 ${t['atr_stop_long']:.2f} | "
        f"目標① ${t['atr_target1']:.2f} ② ${t['atr_target2']:.2f}"
    )
    if shares > 0:
        risk_per_share = price - t["atr_stop_long"]
        total_risk = risk_per_share * shares
        lines.append(f"💰 {shares}股風險敞口：每股 ${risk_per_share:.2f} · 總風險 ${total_risk:,.0f}")

    return lines


def render_tsla_tech_panel():
    st.markdown('<div class="section-label">▸ 📐 TSLA 技術分析 · 關鍵位與交易設定</div>',
                unsafe_allow_html=True)
    period = st.session_state.get("tech_period", "3mo")
    t = fetch_tsla_technicals(period)

    if t.get("error"):
        st.error(f"技術數據載入失敗：{t['error']}")
        return

    price = t["price"]
    gap_pct = t["gap_pct"]
    gap_html = ""
    if abs(gap_pct) > 0.3:
        g_cls = "gap-up" if gap_pct > 0 else "gap-down"
        g_sym = "↑" if gap_pct > 0 else "↓"
        gap_html = f'<span class="gap-badge {g_cls}">{g_sym}缺口 {gap_pct:+.2f}%</span>'

    # ── Header ──
    now_lbl = datetime.now(pytz.timezone("America/New_York")).strftime("%H:%M ET")
    header = (
        '<div class="tech-wrap">'
        '<div class="tech-header">'
        '<div>'
        '<div class="tech-title">📐 TSLA · 技術關鍵位</div>'
        f'<div style="font-family:var(--mono,monospace);font-size:.6rem;color:var(--muted)">{now_lbl} · {period}</div>'
        '</div>'
        f'<div class="tech-price {cc(price - t["prev"])}">'
        f'${fmt_num(price)}{gap_html}'
        '</div>'
        '</div>'
    )

    # ── EMA / ATR / RSI cards ──
    e20_cls  = "active" if price > t["e20"]  else "warn"
    e50_cls  = "active" if price > t["e50"]  else "warn"
    e200_cls = "active" if price > t["e200"] else "warn"
    rsi_cls  = "warn" if t["rsi"] >= 75 or t["rsi"] <= 30 else "active" if 50 < t["rsi"] < 70 else ""
    macd_cls = "active" if t["macd_hist"] > 0 else "warn"

    grid = '<div class="tech-grid">'
    def _card(label, val, sub, cls=""):
        return (f'<div class="tech-card {cls}">'
                f'<div class="tech-clabel">{label}</div>'
                f'<div class="tech-cval">{val}</div>'
                f'<div class="tech-csub">{sub}</div>'
                f'</div>')

    grid += _card("EMA 20", f"${fmt_num(t['e20'])}",
                  "↑多" if price>t['e20'] else "↓空", e20_cls)
    grid += _card("EMA 50", f"${fmt_num(t['e50'])}",
                  "↑多" if price>t['e50'] else "↓空", e50_cls)
    grid += _card("EMA 200", f"${fmt_num(t['e200'])}",
                  "牛市線上" if price>t['e200'] else "熊市線下", e200_cls)
    grid += _card("ATR 14", f"${t['atr']:.2f}",
                  f"{t['atr_ratio']:.1f}x均值 {'壓縮' if t['atr_ratio']<0.8 else '擴張' if t['atr_ratio']>1.4 else '正常'}")
    grid += _card("RSI 14", f"{t['rsi']:.1f}",
                  "超買" if t['rsi']>=75 else "超賣" if t['rsi']<=30 else "中性", rsi_cls)
    grid += _card("MACD", f"{t['macd']:.3f}",
                  f"{'金叉▲' if t['macd']>t['macd_sig'] else '死叉▼'} Hist {t['macd_hist']:.3f}", macd_cls)
    grid += '</div>'

    # ── Key levels table ──
    levels_html = '<div style="margin:.5rem 0">'
    levels = [
        ("🔴 阻力②",  t['r20h'],          "20日最高/供應區",    "down"),
        ("🔴 阻力①",  t['r5h'],           "5日高點",           "down"),
        ("◆ EMA20",   t['e20'],           "短期均線",           "flat"),
        ("◆ EMA50",   t['e50'],           "中期均線",           "flat"),
        ("✅ 支撐①",  t['r5l'],           "5日低點",           "up"),
        ("✅ 支撐②",  t['r20l'],          "20日最低/需求區",    "up"),
        ("📐 ATR止損", t['atr_stop_long'], "1.5×ATR多單止損",   "down"),
        ("🎯 目標①",  t['atr_target1'],   "2×ATR目標",         "up"),
        ("🎯 目標②",  t['atr_target2'],   "3.5×ATR目標",       "up"),
    ]
    # sort by price descending to show natural level ladder
    levels.sort(key=lambda x: x[1], reverse=True)

    for lbl, lvl, zone, col in levels:
        dist = (lvl - price) / price * 100
        dist_str = f"{dist:+.2f}%"
        # highlight current price between levels
        is_near = abs(dist) < 0.5
        bg_style = "background:var(--flat-bg);" if is_near else ""
        levels_html += (
            f'<div class="level-row" style="{bg_style}">'
            f'<span class="level-label">{lbl}</span>'
            f'<span class="tech-cval {col}">${fmt_num(lvl)}</span>'
            f'<span class="{col}" style="font-size:.68rem">{dist_str}</span>'
            f'<span class="level-zone">{zone}</span>'
            f'</div>'
        )
    levels_html += '</div>'

    # ── Signal summary ──
    shares = st.session_state.get("tsla_shares", 100)
    signals = _tech_signal_summary(t, shares)
    sig_html = '<div class="signal-row">' + "<br>".join(signals) + '</div>'

    st.markdown(header + grid + levels_html + sig_html + '</div>',
                unsafe_allow_html=True)
    return t  # return for Telegram use




# ── #7 DXY + BTC先行指標面板 ──────────────────────────────────────────────────
MACRO_LEAD_TICKERS = {
    "DX=F":   {"label":"DXY 美元",  "unit":"指數",    "corr":"反向",  "corr_cls":"corr-inv",
               "note":"美元強 → 風險資產承壓"},
    "BTC-USD":{"label":"BTC 比特幣","unit":"USD",     "corr":"正向",  "corr_cls":"corr-pos",
               "note":"BTC領先大市15-30分鐘"},
    "GC=F":   {"label":"黃金",      "unit":"USD/盎司","corr":"反向",  "corr_cls":"corr-inv",
               "note":"避險需求指標"},
    "SI=F":   {"label":"白銀",      "unit":"USD/盎司","corr":"混合",  "corr_cls":"",
               "note":"工業+避險雙重屬性"},
}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_macro_leads() -> dict:
    """
    Fetch DXY, BTC, Gold, Silver with pre/post market awareness.
    DXY: tries DX=F first, falls back to UUP (USD ETF) if futures fail.
    Gold/Silver: always fetches daily bars for reliable H/L.
    Returns normalised dict per ticker with spark (5-day trend chars).
    """
    et_t   = datetime.now(pytz.timezone("America/New_York")).time()
    is_pre = time(4, 0) <= et_t < time(9, 30)
    results = {}

    # DXY fallback chain:
    # 1. DX=F  — ICE Dollar Index futures (exact value ~100-110)
    # 2. ^DXY  — Yahoo Finance spot index (same value range)
    # 3. UUP   — Invesco ETF (~$28), pct change only; price scaled to DXY equiv
    DXY_CHAIN = ["DX=F", "^DXY", "UUP"]
    UUP_TO_DXY_FACTOR = 3.73   # UUP * 3.73 ≈ DXY; historical regression constant

    def _yf_daily(tk: str) -> dict | None:
        """Fetch last 7 days of daily bars, return normalised dict."""
        try:
            df = yf.download(tk, period="7d", interval="1d",
                             progress=False, auto_adjust=True)
            if df.empty: return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            price = float(df["Close"].iloc[-1])
            prev  = float(df["Close"].iloc[-2]) if len(df) >= 2 else price
            high  = float(df["High"].iloc[-1])  if "High" in df.columns else None
            low   = float(df["Low"].iloc[-1])   if "Low"  in df.columns else None
            return dict(price=price, prev=prev,
                        reg_chg=price - prev,
                        reg_pct=(price - prev) / prev * 100 if prev else None,
                        pre_price=None, pre_pct=None,
                        high=high, low=low, error=None)
        except Exception:
            return None

    for ticker, meta in MACRO_LEAD_TICKERS.items():
        d = None
        actual_ticker = ticker   # track which ticker succeeded (for UUP fallback)

        if ticker == "DX=F":
            # Try each ticker in the fallback chain
            for _tk in DXY_CHAIN:
                # Layer 1: chart API
                try:
                    d = _yahoo_chart_api(_tk)
                    if d and not d.get("error") and d.get("price"):
                        actual_ticker = _tk
                        break
                except Exception:
                    pass
                # Layer 2: daily download
                d = _yf_daily(_tk)
                if d and d.get("price"):
                    actual_ticker = _tk
                    break
                d = None
        else:
            # Layer 1: chart API
            try:
                d = _yahoo_chart_api(ticker)
            except Exception:
                pass
            # Layer 2: daily download (also provides reliable H/L for futures)
            if d is None or d.get("error") or not d.get("price"):
                d = _yf_daily(ticker)
            # Layer 2b: if chart API succeeded but H/L missing, supplement from daily
            elif d.get("high") is None or d.get("low") is None:
                _daily = _yf_daily(ticker)
                if _daily:
                    if d.get("high") is None: d["high"] = _daily.get("high")
                    if d.get("low")  is None: d["low"]  = _daily.get("low")

        if d is None or d.get("error") or not d.get("price"):
            results[ticker] = dict(meta=meta, error="載入失敗")
            continue

        # Label + price scaling for fallback tickers
        display_meta = dict(meta)
        uup_scaled   = False   # flag: price was scaled from UUP
        if actual_ticker == "^DXY":
            display_meta["label"] = "DXY (現貨)"
            display_meta["note"]  = "Yahoo Finance DXY現貨指數"
        elif actual_ticker == "UUP":
            # UUP price ~$28 — scale to DXY equivalent so display is meaningful
            # pct change is identical (same underlying), so no scaling needed for pct
            display_meta["label"] = "DXY≈ (UUP)"
            display_meta["note"]  = "UUP ETF×3.73代理 — DX=F/^DXY暫不可用"
            uup_scaled = True

        # Pick best price + pct for current session
        if is_pre and d.get("pre_price") and d.get("pre_pct") is not None:
            disp_price  = d["pre_price"]
            disp_pct    = d["pre_pct"]
            session_lbl = "盤前"
        elif d.get("price") and d.get("reg_pct") is not None:
            disp_price  = d["price"]
            disp_pct    = d["reg_pct"]
            session_lbl = "即時" if ticker == "BTC-USD" else "收盤"
        else:
            disp_price  = d.get("price") or d.get("prev")
            disp_pct    = None
            session_lbl = "—"

        # Scale UUP price to DXY-equivalent so display shows ~100-110 not ~$28
        if uup_scaled and disp_price:
            disp_price = disp_price * UUP_TO_DXY_FACTOR
            # Also scale high/low for consistency
            if d.get("high"): d["high"] = d["high"] * UUP_TO_DXY_FACTOR
            if d.get("low"):  d["low"]  = d["low"]  * UUP_TO_DXY_FACTOR

        # 5-day spark from daily closes (reuse _yf_daily data when available)
        spark = ""
        try:
            df5 = yf.download(actual_ticker, period="6d", interval="1d",
                              progress=False, auto_adjust=True)
            if not df5.empty:
                if isinstance(df5.columns, pd.MultiIndex):
                    df5.columns = df5.columns.get_level_values(0)
                closes = df5["Close"].dropna().tolist()[-5:]
                if len(closes) >= 2:
                    lo, hi = min(closes), max(closes)
                    rng = hi - lo or 1
                    bars = "▁▂▃▄▅▆▇█"
                    spark = "".join(bars[min(7, int((c - lo) / rng * 7))] for c in closes)
        except Exception:
            spark = ""

        results[ticker] = dict(
            meta        = display_meta,
            price       = disp_price,
            pct         = disp_pct,
            prev        = d.get("prev"),
            high        = d.get("high"),
            low         = d.get("low"),
            session_lbl = session_lbl,
            spark       = spark,
            actual_tk   = actual_ticker,
            error       = None,
        )
    return results


def _macro_risk_signal(dxy: dict, btc: dict, gold: dict) -> tuple[str, str, str]:
    """
    Synthesise DXY + BTC + Gold into a unified risk-on/off signal.
    Returns (signal_html, bg_color, border_color).
    """
    dxy_pct  = dxy.get("pct")  if dxy  and not dxy.get("error")  else None
    btc_pct  = btc.get("pct")  if btc  and not btc.get("error")  else None
    gold_pct = gold.get("pct") if gold and not gold.get("error") else None
    dxy_p    = dxy.get("price") if dxy  else None

    parts = []

    # ── DXY absolute level ──
    if dxy_p:
        if dxy_p >= 106:
            parts.append(f"DXY {dxy_p:.2f} 偏強水平，風險資產整體承壓")
        elif dxy_p <= 100:
            parts.append(f"DXY {dxy_p:.2f} 偏弱水平，利好風險資產及黃金")

    # ── Composite risk-on/off scoring ──
    score = 0   # positive = risk-on, negative = risk-off
    signals = []

    if dxy_pct is not None:
        if dxy_pct >= 0.5:
            score -= 2
            signals.append(f"DXY {dxy_pct:+.2f}% ↑ 美元走強，科技/TSLA承壓")
        elif dxy_pct <= -0.5:
            score += 2
            signals.append(f"DXY {dxy_pct:+.2f}% ↓ 美元走弱，利好成長股")

    if btc_pct is not None:
        if btc_pct >= 2.0:
            score += 2
            signals.append(f"BTC {btc_pct:+.2f}% ↑ 加密領漲，Risk-On情緒")
        elif btc_pct >= 0.5:
            score += 1
            signals.append(f"BTC {btc_pct:+.2f}% ↑ 輕微Risk-On")
        elif btc_pct <= -2.0:
            score -= 2
            signals.append(f"BTC {btc_pct:+.2f}% ↓ 加密下跌，Risk-Off預警")
        elif btc_pct <= -0.5:
            score -= 1
            signals.append(f"BTC {btc_pct:+.2f}% ↓ 輕微Risk-Off")

    if gold_pct is not None:
        if gold_pct >= 1.0:
            score -= 1
            signals.append(f"黃金 {gold_pct:+.2f}% ↑ 避險需求上升")
        elif gold_pct <= -1.0:
            score += 1
            signals.append(f"黃金 {gold_pct:+.2f}% ↓ 避險鬆動")

    # ── Final verdict ──
    if score >= 3:
        verdict = "🚀 <b>強Risk-On</b> — 多項先行指標同步看多，TSLA做多信號增強"
        bg, bc = "var(--up-bg)", "var(--up)"
    elif score >= 1:
        verdict = "✅ <b>溫和Risk-On</b> — 先行指標偏多，配合技術面做多"
        bg, bc = "var(--up-bg)", "var(--up)"
    elif score <= -3:
        verdict = "🔴 <b>強Risk-Off</b> — 多項先行指標同步看空，謹慎做多"
        bg, bc = "var(--down-bg)", "var(--down)"
    elif score <= -1:
        verdict = "⚠️ <b>溫和Risk-Off</b> — 先行指標偏空，控制倉位"
        bg, bc = "var(--down-bg)", "var(--down)"
    else:
        verdict = "◆ <b>中性</b> — 先行指標無明確方向，跟隨技術面"
        bg, bc = "var(--flat-bg)", "var(--muted)"

    detail = " &nbsp;·&nbsp; ".join(signals) if signals else "先行指標變動溫和"
    return f"{verdict}<br><span style='font-size:.7rem;color:var(--muted)'>{detail}</span>", bg, bc


def _btc_lead_note(btc_pct: float | None) -> str:
    """Generate BTC-specific leading indicator note."""
    if btc_pct is None: return ""
    et_t = datetime.now(pytz.timezone("America/New_York")).time()
    is_pre = time(4, 0) <= et_t < time(9, 30)
    if not is_pre: return ""   # only relevant pre-market
    # BTC leading effect most pronounced pre-market
    if btc_pct >= 3.0:
        return "⚡ BTC盤前急升，通常預示科技股跟升（15-30分鐘滯後）"
    if btc_pct >= 1.5:
        return "📈 BTC盤前上漲，輕微看多科技板塊"
    if btc_pct <= -3.0:
        return "⚠️ BTC盤前急跌，留意科技股開盤承壓"
    if btc_pct <= -1.5:
        return "📉 BTC盤前下跌，科技股開盤略偏弱"
    return ""


def render_macro_lead_panel():
    st.markdown(
        '<div class="section-label">▸ 🌐 宏觀先行指標 · DXY美元 · BTC · 黃金</div>',
        unsafe_allow_html=True)

    with st.spinner("載入先行指標..."):
        data = fetch_macro_leads()

    now_lbl = datetime.now(pytz.timezone("America/New_York")).strftime("%H:%M ET")
    et_t    = datetime.now(pytz.timezone("America/New_York")).time()
    is_pre  = time(4, 0) <= et_t < time(9, 30)

    html = (
        '<div class="macro-lead-wrap">'
        '<div class="macro-lead-header">'
        '<div class="macro-lead-title">🌐 宏觀先行指標</div>'
        f'<div style="font-family:var(--mono,monospace);font-size:.6rem;color:var(--muted)">'
        f'{"盤前模式 — BTC領先效應激活" if is_pre else "盤中/盤後"}'
        f' &nbsp;·&nbsp; {now_lbl}</div>'
        '</div>'
        '<div class="macro-lead-grid">'
    )

    ticker_order = ["DX=F", "BTC-USD", "GC=F", "SI=F"]
    for ticker in ticker_order:
        d = data.get(ticker, {})
        meta = d.get("meta", MACRO_LEAD_TICKERS.get(ticker, {}))

        if d.get("error"):
            html += (
                f'<div class="macro-card">'
                f'<div class="macro-clabel">{meta.get("label", ticker)}</div>'
                f'<div class="macro-cval flat">—</div>'
                f'<div class="macro-chg flat">{d["error"][:25]}</div>'
                f'</div>'
            )
            continue

        price   = d.get("price")
        pct     = d.get("pct")
        high    = d.get("high")
        low     = d.get("low")
        spark   = d.get("spark", "")
        slbl    = d.get("session_lbl", "")
        corr    = meta.get("corr", "")
        corr_cls= meta.get("corr_cls", "")
        note    = meta.get("note", "")
        unit    = meta.get("unit", "")

        col_cls = cc(pct)

        # Card border: risk-off cues = DXY up / BTC down / Gold up
        card_extra = ""
        if ticker == "DX=F"    and (pct or 0) >= 0.5:  card_extra = "risk-off"
        if ticker == "DX=F"    and (pct or 0) <= -0.5: card_extra = "risk-on"
        if ticker == "BTC-USD" and (pct or 0) >= 1.5:  card_extra = "risk-on"
        if ticker == "BTC-USD" and (pct or 0) <= -1.5: card_extra = "risk-off"
        if ticker == "GC=F"    and (pct or 0) >= 1.0:  card_extra = "risk-off"

        # Format price
        actual_tk_used = d.get("actual_tk", ticker)
        if ticker == "BTC-USD" and price and price > 1000:
            price_str = f"${price:,.0f}"
        elif ticker == "DX=F":
            # DX=F, ^DXY, or UUP-scaled all display as index value (no $)
            price_str = f"{price:.2f}" if price else "—"
        else:
            price_str = f"${fmt_num(price)}"

        sign = "+" if (pct or 0) >= 0 else ""
        pct_str = f"{sign}{pct:.2f}%" if pct is not None else "—"

        corr_badge = (
            f'<span class="macro-corr-badge {corr_cls}">{corr}</span>'
            if corr else ""
        )

        html += (
            f'<div class="macro-card {card_extra}">'
            f'{corr_badge}'
            f'<div class="macro-clabel">{meta["label"]}</div>'
            f'<div class="macro-cval {col_cls}">{price_str}</div>'
            f'<div class="macro-chg {col_cls}">{pct_str}'
            f'<span style="font-size:.52rem;color:var(--muted);margin-left:.3rem">[{slbl}]</span>'
            f'</div>'
            f'<div class="macro-meta">'
            f'H {fmt_num(high)} · L {fmt_num(low)}'
            f'</div>'
            f'<div class="macro-spark">{spark}</div>'
            f'</div>'
        )

    html += '</div>'  # close grid

    # BTC leading note (pre-market only)
    btc_d   = data.get("BTC-USD", {})
    btc_pct = btc_d.get("pct") if not btc_d.get("error") else None
    btc_note = _btc_lead_note(btc_pct)
    if btc_note:
        html += (
            f'<div style="font-family:var(--sans,sans-serif);font-size:.74rem;'
            f'padding:.4rem .7rem;background:var(--up-bg);border-left:3px solid var(--up);'
            f'border-radius:0 4px 4px 0;color:var(--up);margin-bottom:.4rem">'
            f'{btc_note}</div>'
        )

    # Unified risk signal
    dxy_d  = data.get("DX=F",    {})
    gold_d = data.get("GC=F",    {})
    signal_html, bg, bc = _macro_risk_signal(dxy_d, btc_d, gold_d)
    html += (
        f'<div class="macro-signal" style="background:{bg};border-left-color:{bc}">'
        f'{signal_html}'
        f'</div>'
        f'</div>'   # close wrap
    )

    st.markdown(html, unsafe_allow_html=True)



# ── #3 TSLA vs QQQ Relative Strength ─────────────────────────────────────────
RS_PAIRS = [
    # (ticker, label_zh, benchmark)
    ("TSLA", "TSLA", "QQQ"),
    ("NVDA", "NVDA", "QQQ"),
    ("AAPL", "AAPL", "QQQ"),
    ("MSFT", "MSFT", "QQQ"),
]

@st.cache_data(ttl=60, show_spinner=False)
def fetch_relative_strength() -> dict:
    """
    Fetch session pct for TSLA, NVDA, AAPL, MSFT vs QQQ benchmark.
    Returns dict keyed by ticker with pct, qqq_pct, rs (difference), 5d/20d avg RS.
    """
    et_t   = datetime.now(pytz.timezone("America/New_York")).time()
    is_pre = time(4,0) <= et_t < time(9,30)
    is_reg = time(9,30) <= et_t < time(16,0)

    def _pct(d: dict) -> float | None:
        if not d or d.get("error"): return None
        if is_pre and d.get("pre_pct") is not None:  return d["pre_pct"]
        if d.get("reg_pct") is not None:              return d["reg_pct"]
        if d.get("pre_pct") is not None:              return d["pre_pct"]
        return None

    # Fetch quotes
    qqq_d   = fetch_quote("QQQ")
    qqq_pct = _pct(qqq_d)

    results = {}
    tickers = list({t for t,_,_ in RS_PAIRS} | {"QQQ"})
    quote_map = {"QQQ": qqq_d}
    for t,_,_ in RS_PAIRS:
        if t not in quote_map:
            quote_map[t] = fetch_quote(t)

    # 20-day historical RS for context (uses daily close)
    hist_rs = {}
    try:
        all_t = [t for t,_,_ in RS_PAIRS] + ["QQQ"]
        df_hist = yf.download(all_t, period="30d", interval="1d",
                              progress=False, auto_adjust=True)
        if isinstance(df_hist.columns, pd.MultiIndex):
            close = df_hist["Close"].dropna(how="all")
        else:
            close = df_hist[["Close"]].rename(columns={"Close": all_t[0]})
        # pct returns
        ret = close.pct_change() * 100
        qqq_ret = ret.get("QQQ", pd.Series(dtype=float))
        for t,_,_ in RS_PAIRS:
            if t in ret.columns and len(qqq_ret) > 0:
                rs_series = ret[t] - qqq_ret
                hist_rs[t] = {
                    "rs_5d":  float(rs_series.tail(5).mean()),
                    "rs_20d": float(rs_series.tail(20).mean()),
                }
    except Exception:
        pass

    for ticker, label, bench in RS_PAIRS:
        d    = quote_map.get(ticker, {})
        pct  = _pct(d)
        rs   = (pct - qqq_pct) if (pct is not None and qqq_pct is not None) else None
        h    = hist_rs.get(ticker, {})
        results[ticker] = dict(
            label   = label,
            pct     = pct,
            qqq_pct = qqq_pct,
            rs      = rs,          # today's RS vs QQQ
            rs_5d   = h.get("rs_5d"),
            rs_20d  = h.get("rs_20d"),
            price   = d.get("pre_price") if is_pre else d.get("price"),
        )
    results["_qqq_pct"] = qqq_pct
    return results


def _rs_verdict(tsla_rs: float | None, rs_5d: float | None) -> tuple[str, str, str]:
    """Return (verdict_text, bg_color, border_color)."""
    if tsla_rs is None:
        return "數據不足", "var(--flat-bg)", "var(--border)"
    if tsla_rs >= 2.0:
        return (f"🚀 <b>TSLA 強勢跑贏</b> QQQ {tsla_rs:+.2f}% — 公司/Musk催化驅動，可考慮重倉",
                "var(--up-bg)", "var(--up)")
    if tsla_rs >= 0.5:
        return (f"✅ <b>TSLA 小幅跑贏</b> QQQ {tsla_rs:+.2f}% — 溫和強勢，跟隨大市做多",
                "var(--up-bg)", "var(--up)")
    if tsla_rs >= -0.5:
        return (f"◆ <b>TSLA 跟隨大市</b>（RS {tsla_rs:+.2f}%）— 大市倉，跟 VIX/QQQ 方向走",
                "var(--flat-bg)", "var(--muted)")
    if tsla_rs >= -2.0:
        return (f"⚠️ <b>TSLA 相對弱勢</b> {tsla_rs:+.2f}% vs QQQ — 避免做多，等強勢確認",
                "var(--down-bg)", "var(--down)")
    return (f"🔴 <b>TSLA 嚴重跑輸</b> QQQ {tsla_rs:+.2f}% — 公司負面催化，做空或觀望",
            "var(--down-bg)", "var(--down)")


def render_relative_strength():
    st.markdown('<div class="section-label">▸ ⚖️ TSLA 相對強弱 vs QQQ</div>',
                unsafe_allow_html=True)
    with st.spinner("計算相對強弱..."):
        rs_data = fetch_relative_strength()

    qqq_pct = rs_data.get("_qqq_pct")
    now_lbl = datetime.now(pytz.timezone("America/New_York")).strftime("%H:%M ET")

    html = (
        '<div class="rs-wrap">'
        '<div class="rs-header">'
        '<div class="rs-title">⚖️ 相對強弱 vs QQQ</div>'
        f'<div style="font-family:var(--mono,monospace);font-size:.6rem;color:var(--muted)">'
        f'QQQ {fmt_pct(qqq_pct)} &nbsp;·&nbsp; {now_lbl}</div>'
        '</div>'
        '<div class="rs-grid">'
    )

    tsla_rs = None
    for ticker, label, _ in RS_PAIRS:
        d   = rs_data.get(ticker, {})
        pct = d.get("pct")
        rs  = d.get("rs")
        r5  = d.get("rs_5d")
        r20 = d.get("rs_20d")

        if ticker == "TSLA": tsla_rs = rs

        # Card class
        if rs is None:          card_cls = ""
        elif rs >= 0.5:         card_cls = "outperform"
        elif rs <= -0.5:        card_cls = "underperform"
        else:                   card_cls = ""

        # Bar: center=50%, each 1% = 5px, capped ±10%
        bar_pct   = min(max((rs or 0), -10), 10)   # clamp -10 to +10
        bar_left  = 50.0
        bar_width = abs(bar_pct) * 2.5              # 2.5% width per 1% RS
        bar_color = "var(--up)" if (rs or 0) >= 0 else "var(--down)"
        if (rs or 0) >= 0:
            bar_style = f"left:{bar_left}%;width:{bar_width}%;background:{bar_color};"
        else:
            bar_style = f"left:{bar_left - bar_width}%;width:{bar_width}%;background:{bar_color};"

        r5_str  = (f"{r5:+.2f}%" if r5  is not None else "—")
        r20_str = (f"{r20:+.2f}%" if r20 is not None else "—")

        html += (
            f'<div class="rs-card {card_cls}">'
            f'<div class="rs-label">{label}</div>'
            f'<div class="rs-val {cc(pct)}">{fmt_pct(pct)}</div>'
            f'<div class="rs-sub">vs QQQ <b class="{cc(rs)}">{fmt_pct(rs)}</b></div>'
            f'<div class="rs-bar-wrap">'
            f'<div class="rs-bar-zero"></div>'
            f'<div class="rs-bar-fill" style="{bar_style}"></div>'
            f'</div>'
            f'<div class="rs-sub">5D均 {r5_str} &nbsp; 20D均 {r20_str}</div>'
            f'</div>'
        )
    html += '</div>'

    # Verdict
    tsla_d   = rs_data.get("TSLA", {})
    verdict, bg, bc = _rs_verdict(tsla_rs, tsla_d.get("rs_5d"))

    # Trend context from 5d/20d
    r5  = tsla_d.get("rs_5d")
    r20 = tsla_d.get("rs_20d")
    trend_txt = ""
    if r5 is not None and r20 is not None:
        if r5 > r20 + 0.3:
            trend_txt = f" &nbsp;·&nbsp; 近5日均RS {r5:+.2f}% 強於20日 {r20:+.2f}%，動能改善"
        elif r5 < r20 - 0.3:
            trend_txt = f" &nbsp;·&nbsp; 近5日均RS {r5:+.2f}% 弱於20日 {r20:+.2f}%，動能惡化"
        else:
            trend_txt = f" &nbsp;·&nbsp; RS趨勢穩定（5D {r5:+.2f}% / 20D {r20:+.2f}%）"

    html += (
        f'<div class="rs-verdict" style="background:{bg};border-left:3px solid {bc}">'
        f'{verdict}{trend_txt}'
        f'</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ── #4 Put/Call Ratio ─────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_put_call_ratio(tickers: list[str] | None = None) -> dict:
    """
    Fetch Put/Call ratio from Yahoo Finance options chain.
    tickers: list of symbols to check. Default: TSLA + SPY.
    Returns dict keyed by ticker: {put_vol, call_vol, pc_ratio, error}
    """
    if tickers is None:
        tickers = ["TSLA", "SPY"]
    results = {}
    for ticker in tickers:
        try:
            t    = yf.Ticker(ticker)
            exp  = t.options          # list of expiry dates
            if not exp:
                results[ticker] = dict(error="no options")
                continue
            # Use nearest expiry (index 0) for most liquid/timely signal
            chain = t.option_chain(exp[0])
            puts  = chain.puts
            calls = chain.calls

            put_vol  = int(puts["volume"].fillna(0).sum())
            call_vol = int(calls["volume"].fillna(0).sum())
            put_oi   = int(puts["openInterest"].fillna(0).sum())
            call_oi  = int(calls["openInterest"].fillna(0).sum())

            pc_vol = put_vol  / call_vol  if call_vol  > 0 else None
            pc_oi  = put_oi   / call_oi   if call_oi   > 0 else None

            # Also aggregate across all expiries for OI (more stable)
            total_put_oi = 0; total_call_oi = 0
            for e in exp[:4]:   # nearest 4 expiries
                try:
                    ch = t.option_chain(e)
                    total_put_oi  += int(ch.puts["openInterest"].fillna(0).sum())
                    total_call_oi += int(ch.calls["openInterest"].fillna(0).sum())
                except Exception:
                    break
            pc_oi_all = total_put_oi / total_call_oi if total_call_oi > 0 else None

            results[ticker] = dict(
                put_vol   = put_vol,
                call_vol  = call_vol,
                put_oi    = put_oi,
                call_oi   = call_oi,
                pc_ratio  = pc_vol,      # volume-based (more timely)
                pc_oi     = pc_oi,       # OI-based nearest expiry
                pc_oi_all = pc_oi_all,   # OI-based all near expiries
                expiry    = exp[0],
                error     = None,
            )
        except Exception as e:
            results[ticker] = dict(error=str(e)[:60])
    return results


def _pc_signal(ratio: float | None, ticker: str) -> tuple[str, str, str, str]:
    """
    Interpret P/C ratio.
    Returns (signal_text, card_class, bg_color, border_color).
    P/C > 1.2  = extreme fear  → contrarian BULLISH (markets often reverse)
    P/C > 0.9  = fearful
    P/C 0.6-0.9 = neutral
    P/C < 0.6  = complacent/greedy → contrarian BEARISH
    P/C < 0.4  = extreme greed → strong contrarian BEARISH
    Note: TSLA has naturally higher P/C than SPY due to hedging demand.
    """
    if ratio is None:
        return "數據不足", "", "var(--flat-bg)", "var(--border)"
    t_label = ticker

    if ratio >= 1.5:
        return (f"🔴 {t_label} 極度恐慌 P/C={ratio:.2f} — 反向指標：做多訊號（峰值恐慌）",
                "extreme-fear", "var(--up-bg)", "var(--up)")
    if ratio >= 1.0:
        return (f"⚠️ {t_label} 市場恐慌 P/C={ratio:.2f} — 偏向看跌，逆勢做多需謹慎",
                "neutral", "var(--flat-bg)", "var(--accent)")
    if ratio >= 0.7:
        return (f"◆ {t_label} 中性 P/C={ratio:.2f} — 無極端情緒，方向跟隨技術面",
                "neutral", "var(--flat-bg)", "var(--border)")
    if ratio >= 0.5:
        return (f"🟡 {t_label} 偏樂觀 P/C={ratio:.2f} — Call主導，留意過度自滿風險",
                "extreme-greed", "var(--down-bg)", "var(--down)")
    return (f"🔴 {t_label} 極度貪婪 P/C={ratio:.2f} — 反向指標：謹慎做多，考慮對沖",
            "extreme-greed", "var(--down-bg)", "var(--down)")


def render_put_call_panel():
    st.markdown('<div class="section-label">▸ 📊 期權 Put/Call Ratio · 情緒極值偵測</div>',
                unsafe_allow_html=True)
    with st.spinner("抓取期權數據..."):
        pc_data = fetch_put_call_ratio(["TSLA", "SPY", "QQQ"])

    now_lbl = datetime.now(pytz.timezone("America/New_York")).strftime("%H:%M ET")

    html = (
        '<div class="pc-wrap">'
        '<div class="pc-header">'
        '<div class="pc-title">📊 Put/Call Ratio</div>'
        f'<div style="font-family:var(--mono,monospace);font-size:.6rem;color:var(--muted)">'
        f'Yahoo Finance 期權鏈 &nbsp;·&nbsp; {now_lbl}</div>'
        '</div>'
        '<div class="pc-grid">'
    )

    signal_rows = []
    for ticker in ["TSLA", "SPY", "QQQ"]:
        d = pc_data.get(ticker, {})
        if d.get("error"):
            html += (
                f'<div class="pc-card">'
                f'<div class="pc-label">{ticker}</div>'
                f'<div class="pc-val flat">—</div>'
                f'<div class="pc-sub">{d["error"][:30]}</div>'
                f'</div>'
            )
            continue

        ratio   = d.get("pc_ratio")      # volume P/C
        oi_rat  = d.get("pc_oi_all")     # OI P/C (all near expiries)
        expiry  = d.get("expiry","")
        put_vol = d.get("put_vol",0)
        call_vol= d.get("call_vol",0)

        sig_txt, card_cls, bg, bc = _pc_signal(ratio, ticker)
        signal_rows.append((sig_txt, bg, bc))

        # Meter: 0.4=left edge, 1.6=right edge, neutral zone 0.6-0.9
        # map ratio to 0-100%: (ratio-0.3)/(1.7-0.3)*100
        meter_pct = max(0, min(100, (((ratio or 0.7) - 0.3) / 1.4) * 100))

        ratio_col = "down" if (ratio or 0) < 0.6 else ("up" if (ratio or 0) > 1.0 else "flat")

        html += (
            f'<div class="pc-card {card_cls}">'
            f'<div class="pc-label">{ticker} · Vol P/C</div>'
            f'<div class="pc-val {ratio_col}">{f"{ratio:.2f}" if ratio else "—"}</div>'
            f'<div class="pc-meter"><div class="pc-needle" style="left:{meter_pct:.0f}%"></div></div>'
            f'<div class="pc-sub">'
            f'Put {fmt_vol(put_vol)} / Call {fmt_vol(call_vol)}'
            f'</div>'
            f'<div class="pc-sub" style="margin-top:.1rem">'
            f'OI比率 <b>{f"{oi_rat:.2f}" if oi_rat else "—"}</b> &nbsp;到期 {expiry}'
            f'</div>'
            f'</div>'
        )
    html += '</div>'

    # Signal rows — TSLA first, most important
    for sig_txt, bg, bc in signal_rows[:1]:   # only TSLA verdict prominent
        html += (
            f'<div class="pc-signal" style="background:{bg};border-left:3px solid {bc}">'
            f'{sig_txt}'
            f'</div>'
        )

    # Combined reading
    tsla_r = pc_data.get("TSLA",{}).get("pc_ratio")
    spy_r  = pc_data.get("SPY",{}).get("pc_ratio")
    if tsla_r is not None and spy_r is not None:
        combo_bg = "var(--flat-bg)"; combo_bc = "var(--border)"
        if tsla_r > 1.2 and spy_r > 0.9:
            combo = "📍 TSLA + SPY 雙雙恐慌 — 市場底部訊號，做多勝率提高"
            combo_bg = "var(--up-bg)"; combo_bc = "var(--up)"
        elif tsla_r < 0.6 and spy_r < 0.6:
            combo = "📍 TSLA + SPY 雙雙貪婪 — 系統性過度樂觀，對沖風險"
            combo_bg = "var(--down-bg)"; combo_bc = "var(--down)"
        elif tsla_r > 1.2 and spy_r < 0.7:
            combo = "📍 TSLA 個股恐慌 / 大市平靜 — TSLA特定風險，避免重倉"
            combo_bg = "var(--flat-bg)"; combo_bc = "var(--accent)"
        elif tsla_r < 0.6 and spy_r > 1.0:
            combo = "📍 TSLA Call主導 / 大市謹慎 — TSLA超樂觀，謹防回調"
            combo_bg = "var(--down-bg)"; combo_bc = "var(--down)"
        else:
            combo = f"SPY P/C {spy_r:.2f} · TSLA P/C {tsla_r:.2f} — 無極端分歧"

        html += (
            f'<div class="pc-signal" style="background:{combo_bg};border-left:3px solid {combo_bc};margin-top:.4rem">'
            f'{combo}'
            f'</div>'
        )

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)



# ── Telegram Push System ───────────────────────────────────────────────────────
def _tg_send(token: str, chat_id: str, text: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    if not token or not chat_id: return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=8)
        return r.json().get("ok", False)
    except Exception:
        return False

def _tg_dedup(text: str) -> str:
    """Return MD5 hash of text for deduplication."""
    import hashlib
    return hashlib.md5(text.encode()).hexdigest()[:12]

def _should_send(msg_hash: str) -> bool:
    hashes = st.session_state.get("tg_sent_hashes", set())
    if msg_hash in hashes: return False
    hashes.add(msg_hash)
    st.session_state["tg_sent_hashes"] = hashes
    return True

def check_and_push_alerts(
    token: str, chat_id: str,
    tsla_data: dict, vix_data: dict,
    yield_data: dict, sector_data: list,
    tech_data: dict | None = None,
) -> list[str]:
    """
    Check all alert conditions and push Telegram messages.
    Returns list of sent message summaries (for UI log).
    """
    if not token or not chat_id: return []
    sent_log = []
    et_now   = datetime.now(pytz.timezone("America/New_York")).strftime("%H:%M ET")
    thr_vix  = st.session_state.get("tg_vix_threshold", 25.0)
    thr_tsla = st.session_state.get("tg_tsla_pct_threshold", 3.0)
    thr_y10  = st.session_state.get("tg_yield_threshold", 4.5)

    def _push(msg: str, emoji: str = "📡"):
        h = _tg_dedup(msg)
        if _should_send(h):
            full = f"{emoji} <b>Fortune Pre-Market</b> · {et_now}\n\n{msg}"
            if _tg_send(token, chat_id, full):
                sent_log.append(msg[:60] + "…" if len(msg) > 60 else msg)

    # ── 1. TSLA price alerts (user-defined) ──
    if tsla_data and not tsla_data.get("error"):
        et_t = datetime.now(pytz.timezone("America/New_York")).time()
        _is_pre = time(4,0) <= et_t < time(9,30)
        cur_price = tsla_data.get("pre_price") if _is_pre else tsla_data.get("price")
        if cur_price:
            for a in st.session_state.get("price_alerts", []):
                if a["ticker"].upper() != "TSLA": continue
                tgt = a["price"]
                if a["direction"] == "突破上方" and cur_price >= tgt:
                    _push(f"🚀 TSLA 突破 <b>${tgt:.2f}</b>！\n現價：<b>${cur_price:.2f}</b>", "🚨")
                elif a["direction"] == "跌破下方" and cur_price <= tgt:
                    _push(f"⚠️ TSLA 跌破 <b>${tgt:.2f}</b>！\n現價：<b>${cur_price:.2f}</b>", "🚨")

    # ── 2. TSLA pre-market big move ──
    if tsla_data and not tsla_data.get("error"):
        pct = tsla_data.get("pre_pct") or tsla_data.get("reg_pct")
        price = tsla_data.get("pre_price") or tsla_data.get("price")
        if pct is not None and abs(pct) >= thr_tsla:
            direction = "急升 🚀" if pct > 0 else "急跌 🔴"
            _push(
                f"TSLA {direction} <b>{pct:+.2f}%</b>\n"
                f"現價：<b>${fmt_num(price)}</b>\n"
                f"閾值：±{thr_tsla:.1f}%",
                "🚨"
            )

    # ── 3. VIX spike ──
    if vix_data and not vix_data.get("error"):
        vix = vix_data.get("price")
        if vix and vix >= thr_vix:
            _push(
                f"VIX 恐慌指數 <b>{vix:.2f}</b> ≥ {thr_vix:.0f}\n"
                f"市場恐慌升溫，注意風險管理",
                "😱"
            )

    # ── 4. 10Y yield threshold ──
    if yield_data:
        y10 = yield_data.get("^TNX", {})
        if not y10.get("error") and y10.get("value"):
            val = y10["value"]
            if val >= thr_y10:
                bp  = y10.get("bp", 0)
                _push(
                    f"10年期美債殖利率 <b>{val:.3f}%</b> ≥ {thr_y10:.1f}%\n"
                    f"今日變動：{bp:+.1f}bp — 科技股估值承壓",
                    "🏦"
                )

    # ── 5. Extreme sector rotation ──
    if sector_data:
        valid = [s for s in sector_data if not s.get("error") and s.get("pct") is not None]
        if len(valid) >= 2:
            top    = valid[0];  bot = valid[-1]
            spread = (top["pct"] or 0) - (bot["pct"] or 0)
            if spread >= 3.0:
                _push(
                    f"板塊極端輪動 (差距 {spread:.1f}%)\n"
                    f"領漲：{top['name_zh']}({top['ticker']}) {fmt_pct(top['pct'])}\n"
                    f"落後：{bot['name_zh']}({bot['ticker']}) {fmt_pct(bot['pct'])}",
                    "🔄"
                )

    # ── 6. ATR compression breakout (if tech data available) ──
    if tech_data and not tech_data.get("error"):
        if tech_data.get("atr_ratio", 1) < 0.65:
            atr = tech_data["atr"]
            _push(
                f"TSLA ATR壓縮 ({tech_data['atr_ratio']:.2f}x均值)\n"
                f"ATR=${atr:.2f} — 蓄勢待發，注意方向突破\n"
                f"突破上方 ${tech_data['atr_target1']:.2f} / 下方 ${tech_data['atr_stop_long']:.2f}",
                "⚡"
            )

    return sent_log


def render_telegram_panel(tsla_data, vix_data, yield_data, sector_data, tech_data=None):
    """Render Telegram push log in sidebar — call after all data fetched."""
    if not st.session_state.get("tg_token") or not st.session_state.get("tg_chat_id"):
        return

    log = check_and_push_alerts(
        st.session_state["tg_token"],
        st.session_state["tg_chat_id"],
        tsla_data, vix_data, yield_data, sector_data, tech_data
    )
    if log:
        html = '<div class="tg-log">'
        now  = datetime.now(pytz.timezone("America/New_York")).strftime("%H:%M")
        for item in log:
            html += f'<div class="tg-log-item">📤 {now} — {_html.escape(item)}</div>'
        html += '</div>'
        st.markdown(
            f'<div class="section-label">▸ 📲 Telegram 推送記錄</div>'
            f'<div class="tg-panel">{html}</div>',
            unsafe_allow_html=True)



# ── News intel panel ──────────────────────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def fetch_news(query: str, serper_key: str, cache_buster: int = 0) -> list:
    if not serper_key: return []
    today = _today_et_str()
    try:
        r = requests.post("https://google.serper.dev/news",
            headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
            json={"q": f"{query} {today}", "num": 8, "hl": "en", "gl": "us", "tbs": "qdr:d"},
            timeout=8)
        articles = r.json().get("news", [])
        fresh, stale = [], []
        for a in articles:
            ds = a.get("date","")
            is_fresh = ("hour" in ds or "minute" in ds or "just now" in ds.lower()
                        or today in ds or ds == "")
            a["_fresh"] = is_fresh
            (fresh if is_fresh else stale).append(a)
        return (fresh + stale)[:6]
    except Exception:
        return []

@st.cache_data(ttl=180, show_spinner=False)
def groq_news_summary(articles: list, topic: str, groq_key: str, cache_buster: int = 0) -> dict:
    if not articles or not groq_key:
        return {"summary":"","signal":"neutral","signal_reason":"","bullets":[],"tsla_impact":"","stale_warning":False}
    today = _today_et_str()
    tagged = []
    stale_count = 0
    for a in articles[:6]:
        fresh_tag = "🟢 今日" if a.get("_fresh", True) else "🔴 舊聞"
        if not a.get("_fresh", True): stale_count += 1
        tagged.append(f"[{fresh_tag}] 標題：{a.get('title','')}\n來源：{a.get('source','')} | 時間：{a.get('date','未知')}\n內容：{a.get('snippet','')}")
    block = "\n\n".join(tagged)
    has_stale = stale_count > len(articles[:6]) // 2
    prompt = f"""你是美股即時交易員分析師。今日日期：{today}（美東時間）
分析以下「{topic}」新聞，**只根據標記為🟢今日的新聞**生成摘要。
若所有新聞都是🔴舊聞，請在 summary 開頭說明「⚠️ 未找到今日最新消息，以下為近期背景資訊」。
新聞：\n{block}
輸出純 JSON（無其他文字、無 markdown）：
{{"signal":"bullish|bearish|neutral","signal_reason":"15字內","summary":"2-3句","bullets":[{{"text":"重點1","level":"red|amber|green"}},{{"text":"重點2","level":"red|amber|green"}}],"tsla_impact":"TSLA今日一句影響","stale_warning":{str(has_stale).lower()}}}"""
    try:
        raw = groq_chat(prompt, groq_key, max_tokens=900, temperature=0.2)
        raw = raw.replace("```json","").replace("```","").strip()
        result = json.loads(raw)
        result["stale_warning"] = result.get("stale_warning", has_stale)
        return result
    except Exception:
        return {"summary":"AI 摘要失敗","signal":"neutral","signal_reason":"","bullets":[],"tsla_impact":"","stale_warning":False}

def render_intel_panel(title: str, query: str, serper_key: str, groq_key: str, icon: str = "📡"):
    st.markdown(f'<div class="section-label">▸ {icon} {title}</div>', unsafe_allow_html=True)
    if not serper_key:
        st.markdown('<div class="intel-panel"><div style="font-size:.75rem;color:var(--muted);text-align:center;padding:1rem">請輸入 Serper API Key</div></div>',
                    unsafe_allow_html=True)
        return

    # FIX #7: manual refresh button per panel
    refresh_key = f"news_refresh_{title}"
    buster = st.session_state.news_refresh.get(title, 0)
    col_t, col_btn = st.columns([8,1])
    with col_btn:
        if st.button("🔄", key=f"refresh_btn_{title}", help="手動刷新此面板"):
            new_buster = int(time_module.time())
            st.session_state.news_refresh[title] = new_buster
            buster = new_buster

    with st.spinner(f"抓取 {title}..."):
        articles = fetch_news(query, serper_key, cache_buster=buster)
    if not articles:
        st.markdown('<div class="intel-panel"><div style="color:var(--muted);font-size:.78rem;padding:.4rem">暫無最新消息</div></div>',
                    unsafe_allow_html=True)
        return
    ai = {}
    if groq_key:
        with st.spinner("Groq 分析中..."):
            ai = groq_news_summary(articles, title, groq_key, cache_buster=buster)

    signal    = ai.get("signal","neutral")
    sig_cls   = {"bullish":"signal-bullish","bearish":"signal-bearish"}.get(signal,"signal-neutral")
    sig_text  = {"bullish":"▲ 利多","bearish":"▼ 利空","neutral":"◆ 中性"}.get(signal,"◆ 中性")
    sig_reason= ai.get("signal_reason","")
    summary   = ai.get("summary","")
    bullets   = ai.get("bullets",[])
    tsla_imp  = ai.get("tsla_impact","")
    stale_warn= ai.get("stale_warning",False)
    now_str   = datetime.now(pytz.timezone("America/New_York")).strftime("%H:%M ET")
    today     = _today_et_str()
    fresh_count = sum(1 for a in articles if a.get("_fresh",True))
    total_count = len(articles)

    html = '<div class="intel-panel">'
    html += f'<div class="intel-header">'
    html += f'<div class="intel-title">{_html.escape(title)}<span class="signal-badge {sig_cls}">{sig_text} {_html.escape(sig_reason)}</span></div>'
    if   fresh_count == total_count: freshness = '<span style="color:var(--up);font-size:.6rem">● 全部今日</span>'
    elif fresh_count == 0:           freshness = '<span style="color:var(--down);font-size:.6rem">⚠ 無今日消息</span>'
    else:                            freshness = f'<span style="color:#D4A017;font-size:.6rem">◑ {fresh_count}/{total_count} 今日</span>'
    html += f'<div class="intel-time">{freshness} &nbsp;Groq · {now_str}</div></div>'
    if stale_warn or fresh_count == 0:
        html += (f'<div style="background:#FFF3CD;border-left:3px solid #D4A017;border-radius:0 4px 4px 0;'
                 f'padding:.4rem .8rem;font-size:.72rem;color:#856404;margin-bottom:.6rem">'
                 f'⚠️ 未找到 {today} 的最新消息，以下為近期背景資訊，請自行核實</div>')
    if summary:
        html += f'<div class="intel-summary">{_html.escape(summary)}</div>'
    if bullets:
        for b in bullets:
            dc = {"red":"red","amber":"amber"}.get(b.get("level",""),"")
            html += (f'<div class="news-item"><div class="news-dot {dc}"></div>'
                     f'<div><div class="news-text">{_html.escape(b.get("text",""))}</div></div></div>')
    html += '<div style="margin-top:.6rem;padding-top:.5rem;border-top:1px solid var(--border)">'
    for a in articles[:5]:
        is_fresh = a.get("_fresh",True)
        dot_col  = "var(--up)" if is_fresh else "var(--down)"
        tag      = "今日" if is_fresh else "舊聞"
        html += (f'<div class="news-item"><div class="news-dot" style="background:{dot_col}"></div>'
                 f'<div><div class="news-text">{_html.escape(a.get("title",""))}</div>'
                 f'<div class="news-source" style="color:{dot_col}">[{tag}] {_html.escape(a.get("source",""))} · {_html.escape(a.get("date",""))}</div>'
                 f'</div></div>')
    html += '</div>'
    if tsla_imp:
        html += (f'<div style="margin-top:.65rem;padding-top:.55rem;border-top:1px solid var(--border);'
                 f'font-family:var(--mono,monospace);font-size:.68rem;color:var(--muted)">'
                 f'🚗 TSLA 影響：<span style="color:var(--text)">{_html.escape(tsla_imp)}</span></div>')
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ── AI Prompt Generator ───────────────────────────────────────────────────────
def generate_trading_prompt(events, oil_data, tsla_data, vix_data, qqq_data, is_pre) -> str:
    et        = pytz.timezone("America/New_York")
    now_et    = datetime.now(et)
    today_str = now_et.strftime("%Y-%m-%d")
    session   = "盤前" if is_pre else "盤中/盤後"
    today_events = next((d.get("events",[]) for d in events if d["date"] == today_str), [])
    events_lines = "\n".join(
        [f"  - [{e.get('impact','').upper()}] {e.get('et_time','')+'ET ' if e.get('et_time') else ''}{e['text']} — {e.get('note','')}"
         for e in today_events]
    ) or "  （今日無已知重大事件）"
    high_events = [e for e in today_events if e.get("impact") == "high"]
    high_lines  = "\n".join([f"  ⚠️ {e.get('et_time','')+'ET ' if e.get('et_time') else ''}{e['text']} — {e.get('note','')}" for e in high_events]) or "  （今日無已確認高影響事件）"

    _et_t = datetime.now(pytz.timezone("America/New_York")).time()
    _is_pre_t  = time(4,0)  <= _et_t < time(9,30)
    _is_reg_t  = time(9,30) <= _et_t < time(16,0)
    _is_post_t = time(16,0) <= _et_t < time(20,0)
    def snap(d):
        if not d or d.get("error"): return "N/A"
        if _is_pre_t and d.get("pre_price") and d.get("pre_pct") is not None:
            p,pct,tag = d["pre_price"],d["pre_pct"],"盤前"
        elif _is_reg_t and d.get("price") and d.get("reg_pct") is not None:
            p,pct,tag = d["price"],d["reg_pct"],"盤中"
        elif _is_post_t and d.get("post_price") and d.get("post_pct") is not None:
            p,pct,tag = d["post_price"],d["post_pct"],"盤後"
        elif d.get("price") and d.get("reg_pct") is not None:
            p,pct,tag = d["price"],d["reg_pct"],"收盤"
        elif d.get("pre_price") and d.get("pre_pct") is not None:
            p,pct,tag = d["pre_price"],d["pre_pct"],"盤前"
        else: p,pct,tag = d.get("price") or d.get("prev"),None,"收盤"
        return f"{fmt_num(p)} {fmt_pct(pct) if pct is not None else '—'} [{tag}]"

    wti   = (oil_data or {}).get("CL=F",{})
    brent = (oil_data or {}).get("BZ=F",{})
    wti_pct   = wti.get("pct")
    wti_str   = f"${fmt_num(wti.get('price'))} ({fmt_pct(wti_pct)})" if wti.get("price") else "N/A"
    brent_str = f"${fmt_num(brent.get('price'))} ({fmt_pct(brent.get('pct'))})" if brent.get("price") else "N/A"
    wti_dir   = _oil_direction_label(wti_pct)
    vix_val   = fmt_num(vix_data.get("price")) if vix_data and not vix_data.get("error") else "N/A"
    fetch_time = datetime.now(pytz.timezone("America/New_York")).strftime("%H:%M:%S ET")

    # Add yield + sector data to prompt
    yield_lines = ""
    try:
        yd = fetch_yields()
        y_parts = []
        for tk, yd_item in yd.items():
            if not yd_item.get("error") and yd_item.get("value"):
                bp = yd_item.get("bp",0)
                bp_s = f"+{bp:.1f}" if bp >= 0 else f"{bp:.1f}"
                y_parts.append(f'{yd_item["label"]} {yd_item["value"]:.3f}% ({bp_s}bp)')
        yield_lines = " | ".join(y_parts)
    except Exception:
        yield_lines = "N/A"

    sector_lines = ""
    try:
        secs = fetch_sectors()
        valid_s = [s for s in secs if not s.get("error") and s["pct"] is not None]
        if valid_s:
            top3    = " > ".join([f'{s["name_zh"]}({fmt_pct(s["pct"])})' for s in valid_s[:3]])
            bottom2 = " | ".join([f'{s["name_zh"]}({fmt_pct(s["pct"])})' for s in valid_s[-2:]])
            sector_lines = f"領漲：{top3} | 落後：{bottom2}"
    except Exception:
        sector_lines = "N/A"

    # Add DXY + BTC data to prompt
    macro_lines = ""
    try:
        _ml = fetch_macro_leads()
        _parts = []
        for _tk, _lbl in [("DX=F","DXY"),("BTC-USD","BTC"),("GC=F","黃金")]:
            _md = _ml.get(_tk, {})
            if not _md.get("error") and _md.get("price"):
                _p   = _md["price"]
                _pct = _md.get("pct")
                _pct_s = f"{_pct:+.2f}%" if _pct is not None else "—"
                if _tk == "BTC-USD" and _p > 1000:
                    _pstr = f"${_p:,.0f}"
                elif _tk == "DX=F":
                    _pstr = f"{_p:.3f}"
                else:
                    _pstr = f"${fmt_num(_p)}"
                _parts.append(f"{_lbl} {_pstr}({_pct_s})")
        macro_lines = " | ".join(_parts)
    except Exception:
        macro_lines = "N/A"

    # Add RS data to prompt
    rs_lines = ""
    try:
        _rs = fetch_relative_strength()
        tsla_rs = _rs.get("TSLA",{})
        qqq_p   = _rs.get("_qqq_pct")
        if tsla_rs.get("rs") is not None:
            rs_lines = (
                f"TSLA今日RS vs QQQ: {tsla_rs['rs']:+.2f}% "
                f"({'跑贏' if tsla_rs['rs']>0 else '跑輸'}) | "
                f"5日均RS: {tsla_rs.get('rs_5d',0):+.2f}% | "
                f"20日均RS: {tsla_rs.get('rs_20d',0):+.2f}% | "
                f"QQQ今日: {fmt_pct(qqq_p)}"
            )
    except Exception:
        rs_lines = "N/A"

    # Add P/C data to prompt
    pc_lines = ""
    try:
        _pc = fetch_put_call_ratio(["TSLA","SPY"])
        tsla_pc = _pc.get("TSLA",{})
        spy_pc  = _pc.get("SPY",{})
        if not tsla_pc.get("error") and tsla_pc.get("pc_ratio"):
            pc_lines = (
                f"TSLA P/C(Vol)={tsla_pc['pc_ratio']:.2f} "
                f"OI={tsla_pc.get('pc_oi_all','—'):.2f if isinstance(tsla_pc.get('pc_oi_all'),float) else '—'} | "
                f"SPY P/C(Vol)={spy_pc.get('pc_ratio','—'):.2f if isinstance(spy_pc.get('pc_ratio'),float) else '—'}"
            )
    except Exception:
        pc_lines = "N/A"

    # Add TSLA tech data to prompt if available
    tech_lines = ""
    try:
        _t = fetch_tsla_technicals(st.session_state.get("tech_period","3mo"))
        if not _t.get("error"):
            tech_lines = (
                f"EMA20=${fmt_num(_t['e20'])} EMA50=${fmt_num(_t['e50'])} EMA200=${fmt_num(_t['e200'])} | "
                f"ATR=${_t['atr']:.2f}({_t['atr_ratio']:.1f}x) | "
                f"RSI={_t['rsi']:.1f} | "
                f"{'多頭對齊' if _t['bull_align'] else '空頭對齊' if _t['bear_align'] else 'EMA混亂'} | "
                f"MACD {'金叉' if _t['macd']>_t['macd_sig'] else '死叉'} | "
                f"止損=${_t['atr_stop_long']:.2f} 目標①=${_t['atr_target1']:.2f}"
            )
    except Exception:
        tech_lines = "N/A"

    return f"""# 美股即時分析請求
日期：{today_str}  時間：{fetch_time}  時段：{session}  數據抓取：{fetch_time}

## 今日全部宏觀事件
{events_lines}

## 今日高影響事件（重點）
{high_lines}

## 市場即時快照
| 指標 | 數值 |
|------|------|
| TSLA | {snap(tsla_data)} |
| QQQ  | {snap(qqq_data)} |
| VIX  | {vix_val} |
| WTI 原油 | {wti_str} |
| Brent 原油 | {brent_str} |
| 美債殖利率 | {yield_lines} |
| 板塊輪動 | {sector_lines} |
| 宏觀先行 | {macro_lines} |
| 相對強弱 | {rs_lines} |
| Put/Call | {pc_lines} |
| TSLA技術 | {tech_lines} |

## 請幫我分析：
1. **今日最大風險/機會**是什麼？結合DXY/BTC先行指標，對 TSLA 和納指方向的影響？
2. **油價{wti_dir} {wti_str}** 對今日科技股有何具體影響？
3. **TSLA 今日交易策略**：根據上方技術數據，建議具體入場區間、止損位（參考ATR止損）、目標位（$數字）？
4. **VIX {vix_val}** 顯示市場情緒如何？適合做多/做空/觀望？
5. 今日最需要關注的**時間點**時序表（請列出今日所有已知ET時間，格式：HH:MM — 事件 — 預期影響方向）？

**已知固定時間點參考**（請確認今日是否有以下發布）：
- 08:30 ET — 若有CPI/PPI/非農/零售/PCE/初領失業金
- 10:00 ET — 若有密歇根消費者信心/ISM
- 13:00 ET — Baker Hughes鑽井數（週五）
- 14:00 ET — 若有FOMC利率決議
- 14:30 ET — 若有Fed主席記者會
- 盤後 — 若有科技財報（TSLA/NVDA/MSFT等）
- TSLA Q2交付數據通常7月第一個工作日約06:00 ET發布

請用繁體中文回答，要具體，每點包含數字區間。"""


# ── Watchlists ────────────────────────────────────────────────────────────────
WATCHLISTS = {
    "核心持倉": [("TSLA","特斯拉"),("NVDA","輝達"),("AAPL","蘋果"),("MSFT","微軟"),("AMZN","亞馬遜")],
    "指數ETF":  [("QQQ","納指100 ETF"),("SPY","標普500 ETF"),("IWM","羅素2000 ETF"),("DIA","道指 ETF")],
    "波動/恐慌":[("^VIX","VIX 恐慌指數"),("UVXY","短期波動 2x"),("SQQQ","納指3x反向"),("TQQQ","納指3x正向")],
    "槓桿ETF":  [("TSLL","TSLA 2x多"),("SOXL","半導體3x"),("FNGU","科技8x")],
    "期貨代理": [("NQ=F","納指期貨"),("ES=F","標普期貨"),("YM=F","道指期貨"),("GC=F","黃金期貨"),("CL=F","原油期貨")],
}


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    inject_css()

    # FIX #1: non-blocking autorefresh (must be called early)
    setup_autorefresh()

    now_et, session = get_session_info()
    is_pre  = "盤前" in session or "隔夜" in session
    is_post = "盤後" in session

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ 設定")

        # FIX #11: dark mode toggle
        dark = st.toggle("🌙 深色模式", value=st.session_state.dark_mode)
        if dark != st.session_state.dark_mode:
            st.session_state.dark_mode = dark
            st.rerun()

        st.markdown("---")
        auto = st.toggle("⏱️ 自動刷新", value=st.session_state.auto_refresh)
        st.session_state.auto_refresh = auto
        if auto:
            iv = st.selectbox("刷新頻率（秒）",[30,60,120,300],index=1,format_func=lambda x:f"{x} 秒")
            st.session_state.refresh_interval = iv
            st.caption(f"下次刷新：每 {iv} 秒自動更新（非阻塞）")

        st.markdown("---")
        st.markdown("### 🔑 API 設定")
        sk = st.text_input("Serper API Key", value=st.session_state.serper_key,
                           type="password", placeholder="新聞抓取 — serper.dev 免費")
        st.session_state.serper_key = sk
        gk = st.text_input("Groq API Key", value=st.session_state.groq_key,
                           type="password", placeholder="AI 摘要 — groq.com 免費")
        st.session_state.groq_key = gk

        st.markdown("---")
        st.markdown("### 📲 Telegram 推送")
        tg_tok = st.text_input("Bot Token", value=st.session_state.tg_token,
                               type="password", placeholder="從 @BotFather 獲取")
        st.session_state.tg_token = tg_tok
        tg_cid = st.text_input("Chat ID", value=st.session_state.tg_chat_id,
                               placeholder="你的 chat_id 或群組 id")
        st.session_state.tg_chat_id = tg_cid
        if tg_tok and tg_cid:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.session_state.tg_vix_threshold = st.number_input(
                    "VIX閾值", value=float(st.session_state.tg_vix_threshold),
                    min_value=15.0, max_value=50.0, step=0.5, format="%.1f")
            with c2:
                st.session_state.tg_tsla_pct_threshold = st.number_input(
                    "TSLA±%", value=float(st.session_state.tg_tsla_pct_threshold),
                    min_value=1.0, max_value=10.0, step=0.5, format="%.1f")
            with c3:
                st.session_state.tg_yield_threshold = st.number_input(
                    "10Y殖利率%", value=float(st.session_state.tg_yield_threshold),
                    min_value=3.0, max_value=6.0, step=0.1, format="%.1f")
            if st.button("🔔 測試推送"):
                _test_msg = "✅ <b>Fortune Pre-Market Monitor</b> Telegram 連接成功！推送系統已就緒。"
                ok = _tg_send(tg_tok, tg_cid, _test_msg)
                st.success("推送成功！") if ok else st.error("推送失敗，請檢查 Token/Chat ID")

        st.markdown("---")
        st.markdown("### 📐 技術分析設定")
        st.session_state.tsla_shares = st.number_input(
            "TSLA 持股數（風險計算）",
            value=int(st.session_state.tsla_shares),
            min_value=0, max_value=10000, step=10)
        st.session_state.tech_period = st.selectbox(
            "技術分析週期",
            ["1mo","3mo","6mo","1y"], index=1,
            format_func=lambda x: {"1mo":"1個月","3mo":"3個月","6mo":"6個月","1y":"1年"}[x])

        st.markdown("---")
        render_alert_manager()

        st.markdown("---")
        st.markdown("### 📋 自訂股票")
        custom = st.text_area("輸入代號（換行分隔）", value=st.session_state.custom_tickers,
                              height=90, placeholder="GOOGL\nMETA")
        st.session_state.custom_tickers = custom

        st.markdown("---")
        st.markdown("### 顯示選項")
        show_macro   = st.checkbox("DXY/BTC先行",    value=True)
        show_rs      = st.checkbox("TSLA相對強弱",   value=True)
        show_pc      = st.checkbox("Put/Call Ratio", value=True)
        show_tech    = st.checkbox("TSLA技術分析",   value=True)
        show_futures = st.checkbox("期貨代理",      value=True)
        show_vix     = st.checkbox("波動/恐慌",     value=True)
        show_lev     = st.checkbox("槓桿ETF",       value=False)
        show_oil     = st.checkbox("能源價格",       value=True)
        show_fg      = st.checkbox("恐懼貪婪指數",  value=True)
        show_yield   = st.checkbox("美債殖利率",     value=True)
        show_sector  = st.checkbox("板塊輪動",       value=True)
        show_trump   = st.checkbox("Trump 消息",    value=True)
        show_iran    = st.checkbox("伊朗/油價新聞", value=True)
        show_fed     = st.checkbox("Fed 官員表態",  value=True)
        show_earnings= st.checkbox("科技財報動態",  value=True)
        show_china   = st.checkbox("中美貿易/台灣", value=True)

        st.markdown("---")
        if st.button("🔄 立即刷新全部"):
            st.cache_data.clear()
            st.session_state.weekly_events = None
            st.rerun()
        if st.button("🗓️ 重新生成週曆"):
            st.session_state.weekly_events = None
            st.session_state.weekly_events_fetched = ""
            st.rerun()

    # ── Header ────────────────────────────────────────────────────────────────
    # Build as string concat — triple-quote f-string with strftime % can break markdown parser
    _iv   = st.session_state.refresh_interval
    _rbadge = (
        '<span style="font-family:var(--mono,monospace);font-size:.6rem;'
        'color:var(--up,#3A7D5C);margin-left:.4rem">&#9203; ' + str(_iv) + 's</span>'
    ) if st.session_state.auto_refresh else ""
    _date = now_et.strftime("%Y-%m-%d")
    _time = now_et.strftime("%H:%M:%S")
    _hdr  = (
        '<div class="pm-header">'
        '<div>'
        '<div class="pm-title">&#128197; Pre-Market Monitor'
        '<span class="pm-session-badge">' + session + '</span>'
        + _rbadge +
        '</div>'
        '<div class="pm-subtitle">美股盤前即時監控 &middot; Fortune Trading Desk &middot; Groq AI &middot; v4</div>'
        '</div>'
        '<div class="pm-clock">' + _date + '<br><b>' + _time + ' ET</b></div>'
        '</div>'
    )
    st.markdown(_hdr, unsafe_allow_html=True)

    if is_pre:
        st.markdown('<div class="alert-box">⏰ <b>盤前交易時段</b> — 流動性較低，請注意風險管理</div>', unsafe_allow_html=True)
    elif is_post:
        st.markdown('<div class="alert-box">🌙 <b>盤後交易時段</b> — 財報/消息驅動，缺口風險較高</div>', unsafe_allow_html=True)

    # ── Weekly calendar ───────────────────────────────────────────────────────
    with st.spinner("📅 載入本週事件日曆..."):
        events = fetch_weekly_events(st.session_state.serper_key, st.session_state.groq_key)
    is_ai = bool(st.session_state.serper_key and st.session_state.groq_key and st.session_state.weekly_events)
    source_label = "✨ Groq AI 自動生成 · 每週一自動更新" if is_ai else "📋 內置數據 · 輸入 Serper + Groq Key 啟用自動更新"
    render_weekly_calendar(events, source_label)

    # ── AI Prompt ─────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">▸ 🤖 AI 交易分析助手</div>', unsafe_allow_html=True)
    col_btn1, col_btn2, col_toast = st.columns([1.5, 1.5, 5])
    with col_btn1:
        if st.button("✨ 一鍵生成 AI Prompt"):
            with st.spinner("整合最新市場數據中..."):
                fetch_quote.clear(); fetch_oil_data.clear()
                oil_data  = fetch_oil_data()
                tsla_data = fetch_quote("TSLA")
                vix_data  = fetch_quote("^VIX")
                qqq_data  = fetch_quote("QQQ")
            st.session_state.ai_prompt = generate_trading_prompt(events, oil_data, tsla_data, vix_data, qqq_data, is_pre)
            st.session_state.show_prompt = True
            st.session_state.prompt_copied = False
    with col_btn2:
        if st.session_state.show_prompt and st.button("❌ 隱藏 Prompt"):
            st.session_state.show_prompt = False

    if st.session_state.show_prompt and st.session_state.ai_prompt:
        st.markdown(
            '<div class="prompt-panel">'
            '<div class="prompt-title">📋 複製以下 Prompt，貼入 ChatGPT / Claude / Gemini</div>'
            '</div>',
            unsafe_allow_html=True)
        # st.code() provides the native copy icon (top-right of code block) — most reliable in Streamlit Cloud
        st.code(st.session_state.ai_prompt, language="markdown")

        # Secondary copy button using st.components.v1.html() — runs in its own iframe
        # so it has proper clipboard permissions, unlike st.markdown <script> which is stripped
        import streamlit.components.v1 as _stc
        # Escape chars that would break the JS template literal
        _pe = st.session_state.ai_prompt
        _pe = _pe.replace("\\", "\\\\")  # backslash first
        _pe = _pe.replace("`", "\\`")          # backtick
        _pe = _pe.replace("${", "\\${")        # template literal interpolation
        _prompt_escaped = _pe
        _copy_html = f"""
<style>
  #copy-btn {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: .73rem;
    background: #6B7C6E;
    color: #FAF7F2;
    border: none;
    border-radius: 4px;
    padding: .38rem 1.1rem;
    cursor: pointer;
    transition: background .2s;
  }}
  #copy-btn:hover {{ background: #5a6b5d; }}
  #copy-btn.success {{ background: #3A7D5C; }}
  #hint {{ font-family: monospace; font-size: .65rem; color: #8A8278; margin-left: .6rem; }}
</style>
<button id="copy-btn" onclick="doCopy()">📋 複製 Prompt</button>
<span id="hint">或點擊代碼框右上角複製圖示</span>
<script>
function doCopy() {{
  const text = `{_prompt_escaped}`;
  // Method 1: modern clipboard API (works when page has focus)
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text)
      .then(onSuccess)
      .catch(() => fallback(text));
  }} else {{
    fallback(text);
  }}
}}
function fallback(text) {{
  // Method 2: execCommand — works inside iframes without clipboard permission
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
  document.body.appendChild(ta);
  ta.focus(); ta.select();
  try {{
    document.execCommand('copy');
    onSuccess();
  }} catch(e) {{
    document.getElementById('hint').innerText = '⚠️ 請手動選取代碼框文字複製';
  }}
  document.body.removeChild(ta);
}}
function onSuccess() {{
  const btn = document.getElementById('copy-btn');
  btn.innerText = '✅ 已複製！';
  btn.classList.add('success');
  setTimeout(() => {{
    btn.innerText = '📋 複製 Prompt';
    btn.classList.remove('success');
  }}, 3000);
}}
</script>"""
        _stc.html(_copy_html, height=48)

    # ── Stock sections ────────────────────────────────────────────────────────
    all_sections = {"核心持倉": WATCHLISTS["核心持倉"], "指數ETF": WATCHLISTS["指數ETF"]}
    if show_vix:     all_sections["波動/恐慌"] = WATCHLISTS["波動/恐慌"]
    if show_lev:     all_sections["槓桿ETF"]   = WATCHLISTS["槓桿ETF"]
    if show_futures: all_sections["期貨代理"]   = WATCHLISTS["期貨代理"]
    if st.session_state.custom_tickers.strip():
        custom_list = [(l.strip().upper(),"") for l in st.session_state.custom_tickers.strip().split("\n") if l.strip()]
        if custom_list: all_sections["自訂監控"] = custom_list
    for sec, tickers in all_sections.items():
        st.markdown(f'<div class="section-label">▸ {sec}</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        for i, (ticker, _) in enumerate(tickers):
            with cols[i % 2]:
                render_quote_card(fetch_quote(ticker), is_pre, is_post)

    if show_oil:
        render_oil_panel()

    # ── Yields ───────────────────────────────────────────────────────────────
    if show_yield:
        render_yield_panel()

    # ── Sector rotation ───────────────────────────────────────────────────────
    if show_sector:
        render_sector_panel()

    # ── Macro Lead Indicators (DXY + BTC + Gold) ────────────────────────────
    if show_macro:
        render_macro_lead_panel()

    # ── Fear & Greed ──────────────────────────────────────────────────────────
    if show_fg:
        st.markdown('<div class="section-label">▸ 😱 市場情緒指標</div>', unsafe_allow_html=True)
        render_fear_greed()

    # ── News panels ───────────────────────────────────────────────────────────
    sk, gk = st.session_state.serper_key, st.session_state.groq_key
    _today = _today_et_str()
    if show_trump:
        render_intel_panel("Trump 最新表態監控", f"Trump Truth Social statement stock market {_today}", sk, gk, "🇺🇸")
    if show_iran:
        render_intel_panel("伊朗戰爭 · 油價消息", f"Iran war oil price Hormuz ceasefire {_today}", sk, gk, "🛢️")
    if show_fed:
        render_intel_panel(
            "Fed 官員表態監控",
            f"Federal Reserve official speech hawkish dovish rate Warsh Powell {_today}",
            sk, gk, "🏦")
    if show_earnings:
        render_intel_panel(
            "科技財報 · 業績動態",
            f"tech earnings results NVDA TSLA MSFT AAPL AMZN guidance {_today}",
            sk, gk, "📊")
    if show_china:
        render_intel_panel(
            "中美貿易 · 台灣局勢",
            f"US China trade tariff Taiwan semiconductor TSLA Shanghai {_today}",
            sk, gk, "🌏")

    # ── TSLA Relative Strength ───────────────────────────────────────────────
    if show_rs:
        render_relative_strength()

    # ── Put/Call Ratio ────────────────────────────────────────────────────────
    if show_pc:
        render_put_call_panel()

    # ── TSLA Technical Panel ─────────────────────────────────────────────────
    tech_result = None
    if show_tech:
        tech_result = render_tsla_tech_panel()

    # ── Quick metrics bar ─────────────────────────────────────────────────────
    st.markdown('<div class="section-label">▸ 快速指標</div>', unsafe_allow_html=True)
    vd = fetch_quote("^VIX"); sd = fetch_quote("SPY")
    qd = fetch_quote("QQQ");  td = fetch_quote("TSLA")
    m1,m2,m3,m4 = st.columns(4)

    def mini(col, lbl, val, sub, col_cls=""):
        col.markdown(f'<div class="mini-card"><div class="mini-label">{lbl}</div>'
                     f'<div class="mini-value {col_cls}">{val}</div>'
                     f'<div class="mini-sub">{sub}</div></div>', unsafe_allow_html=True)

    def best_pct(d):
        if not d or d.get("error"): return None, None, "—"
        et_t = datetime.now(pytz.timezone("America/New_York")).time()
        _is_reg = time(9,30) <= et_t < time(16,0)
        if d.get("pre_pct") is not None and not _is_reg: return d["pre_pct"], d.get("pre_price") or d.get("price"), "盤前"
        if d.get("reg_pct") is not None: return d["reg_pct"], d.get("price"), "盤中" if _is_reg else "收盤"
        if d.get("pre_pct") is not None: return d["pre_pct"], d.get("pre_price") or d.get("price"), "盤前"
        if d.get("post_pct") is not None: return d["post_pct"], d.get("post_price"), "盤後"
        return None, d.get("price"), "—"

    # FIX #8: VIX with yesterday delta
    vp = vd.get("price")
    vp_prev = fetch_vix_prev()
    vc = "down" if (vp and vp>25) else ("up" if (vp and vp<18) else "flat")
    vl = "極度恐慌" if (vp and vp>30) else ("恐慌" if (vp and vp>20) else "平靜")
    vix_delta = ""
    if vp and vp_prev:
        d_val = vp - vp_prev
        vix_delta = f' ({"+" if d_val>=0 else ""}{d_val:.2f} vs昨)'
    mini(m1, "VIX 恐慌", fmt_num(vp), f"{vl}{vix_delta}", vc)

    sp, _, slbl = best_pct(sd)
    mini(m2, f"SPY {slbl}%", fmt_pct(sp), f"收盤 {fmt_num(sd.get('price'))}", cc(sp))
    qp, _, qlbl = best_pct(qd)
    mini(m3, f"QQQ {qlbl}%", fmt_pct(qp), f"收盤 {fmt_num(qd.get('price'))}", cc(qp))
    tp, _, tlbl = best_pct(td)
    mini(m4, f"TSLA {tlbl}%", fmt_pct(tp), f"收盤 {fmt_num(td.get('price'))}", cc(tp))

    # ── Telegram push (runs every refresh cycle) ─────────────────────────────
    if st.session_state.get("tg_token") and st.session_state.get("tg_chat_id"):
        _yield_data  = fetch_yields()  if show_yield  else {}
        _sector_data = fetch_sectors() if show_sector else []
        # Also check DXY extreme move for Telegram alert
        if show_macro:
            _macro_data = fetch_macro_leads()
            _dxy = _macro_data.get("DX=F", {})
            _btc = _macro_data.get("BTC-USD", {})
            _dxy_pct = _dxy.get("pct")
            _btc_pct = _btc.get("pct")
            if _dxy_pct is not None and abs(_dxy_pct) >= 0.8:
                _dir = "急升" if _dxy_pct > 0 else "急跌"
                _dxy_price = _dxy.get('price', 0)
                _dxy_note  = "⚠️ 美元走強，風險資產承壓" if _dxy_pct > 0 else "✅ 美元走弱，利好成長股"
                _msg = f"DXY 美元指數{_dir} {_dxy_pct:+.2f}% 現值：{_dxy_price:.3f} {_dxy_note}"
                import hashlib as _hl
                _h = _hl.md5(_msg.encode()).hexdigest()[:12]
                if _should_send(_h):
                    _tg_send(st.session_state["tg_token"], st.session_state["tg_chat_id"],
                             "🌐 <b>Fortune Pre-Market</b>\n\n" + _msg)
            if _btc_pct is not None and abs(_btc_pct) >= 3.0:
                _dir = "急升" if _btc_pct > 0 else "急跌"
                _btc_price = _btc.get('price', 0)
                _btc_note  = "📈 盤前風險情緒改善，留意科技股跟升" if _btc_pct > 0 else "📉 加密下跌，盤前風險情緒偏弱"
                _msg = f"BTC {_dir} {_btc_pct:+.2f}% 現價：${_btc_price:,.0f} {_btc_note}"
                import hashlib as _hl2
                _h2 = _hl2.md5(_msg.encode()).hexdigest()[:12]
                if _should_send(_h2):
                    _tg_send(st.session_state["tg_token"], st.session_state["tg_chat_id"],
                             "₿ <b>Fortune Pre-Market</b>\n\n" + _msg)
        render_telegram_panel(td, vd, _yield_data, _sector_data, tech_result)

    # ── Footer ────────────────────────────────────────────────────────────────
    next_refresh = f" · ⏱ 自動刷新每 {st.session_state.refresh_interval}s" if st.session_state.auto_refresh else ""
    st.markdown(f"""
    <div style="font-family:var(--mono,monospace);font-size:.62rem;color:var(--muted,#AAA49C);
         text-align:center;padding:1.8rem 0 .8rem;border-top:1px solid var(--border,#D8D0C0);margin-top:1.8rem">
      最後更新 {datetime.now().strftime('%H:%M:%S')}{next_refresh}
      · 股價延遲 15-20 分鐘 · Groq AI 免費版 · 僅供參考，不構成投資建議
    </div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
