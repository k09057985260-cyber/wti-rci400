"""Independent WTI RCI400 mobile aurora; does not modify MACD400."""
import os
import time
from datetime import datetime, timedelta, timezone
from threading import Lock

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from flask import Flask, Response
from scipy.stats import rankdata

app = Flask(__name__)
API_URL = 'https://api.sifting.io/v1/hist/commodities/WTIUSD/bars'
_lock = Lock()
_cache = {'html': None, 'at': 0.0}


def load_bars():
    key = os.environ.get('SIFTING_API_KEY', '').strip()
    if not key:
        raise RuntimeError('RenderのEnvironmentにSIFTING_API_KEYを設定してください。')
    now = datetime.now(timezone.utc)
    resp = requests.get(
        API_URL, headers={'X-API-Key': key},
        params={'start': (now - timedelta(days=6)).strftime('%Y-%m-%d'),
                'end': (now + timedelta(days=1)).strftime('%Y-%m-%d'),
                'interval': '5m', 'order': 'desc', 'limit': 1000},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get('data', [])
    if not data:
        raise RuntimeError('Sifting APIからローソク足を取得できませんでした。')
    df = pd.DataFrame(data)
    df['time'] = pd.to_datetime(df['t'], unit='ms', utc=True)
    for c in ('o', 'h', 'l', 'c'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['time', 'c']).sort_values('time').drop_duplicates('time')
    # API timestamp is assumed to be the bar OPEN time. Hide the currently forming bar.
    completed_before = pd.Timestamp(now).floor('5min')
    df = df[df['time'] < completed_before]
    if len(df) < 400:
        raise RuntimeError(f'RCI400には確定済み5分足400本が必要です。取得済み: {len(df)}本')
    return df.reset_index(drop=True)


def rci_matrix(closes):
    """399 real RCI curves (periods 2..400), using only past and current closes.

    Tied prices use average ranks. Pearson rank correlation avoids the
    classic no-ties formula's bias when prices repeat.
    """
    from numpy.lib.stride_tricks import sliding_window_view
    n = len(closes)
    output = np.full((399, n), np.nan, dtype=np.float32)
    for period in range(2, 401):
        windows = sliding_window_view(closes, period)
        ranks = rankdata(windows, method='average', axis=1)
        centered = ranks - (period + 1) / 2
        time_rank = np.arange(period, dtype=np.float64) - (period - 1) / 2
        denom = np.sqrt((centered * centered).sum(axis=1) * (time_rank @ time_rank))
        values = np.divide(centered @ time_rank, denom,
                           out=np.zeros(len(windows)), where=denom > 0) * 100
        output[period - 2, period - 1:] = values
    return output


def make_chart():
    df = load_bars()
    rci = rci_matrix(df['c'].to_numpy(dtype=np.float64))
    # Display recent 4 hours by default, retain the last 240 bars for panning.
    show = min(240, len(df))
    view = df.iloc[-show:].copy()
    lines = rci[:, -show:]
    times = view['time'].dt.tz_convert('Asia/Tokyo')
    labels = times.dt.strftime('%m/%d %H:%M').tolist()
    x = []
    y = []
    for curve in lines:
        x.extend(labels)
        x.append(None)
        y.extend([None if not np.isfinite(v) else float(v) for v in curve])
        y.append(None)
    fig = go.Figure(go.Scattergl(
        x=x, y=y, mode='lines',
        line=dict(color='rgba(255,255,255,0.13)', width=0.65),
        connectgaps=False, hoverinfo='skip', showlegend=False,
    ))
    fig.update_layout(
        template='plotly_dark', title=dict(text='WTI · RCI400 AURORA · 5分足', font=dict(size=16)),
        height=730, margin=dict(l=38, r=16, t=48, b=68),
        paper_bgcolor='#101829', plot_bgcolor='#101829',
        dragmode='pan', hovermode=False, uirevision='rci400',
    )
    # Every hour has a bold vertical line; half-hours have a lighter one.
    for i, t in enumerate(times):
        if t.minute == 0:
            fig.add_vline(x=i, line_width=1.8, line_color='rgba(250,211,77,0.60)')
        elif t.minute == 30:
            fig.add_vline(x=i, line_width=0.85, line_color='rgba(111,174,234,0.30)')
    hourly = [i for i, t in enumerate(times) if t.minute == 0]
    fig.update_xaxes(type='category', categoryorder='array', categoryarray=labels,
                     tickmode='array', tickvals=[labels[i] for i in hourly],
                     ticktext=[times.iloc[i].strftime('%H:%M') for i in hourly],
                     tickangle=-45, tickfont=dict(size=12), showgrid=False,
                     range=[max(-0.5, show - 49), show - 0.5])
    fig.update_yaxes(range=[-105, 105], tickvals=[-100, -50, 0, 50, 100],
                     gridcolor='rgba(255,255,255,0.16)', zeroline=True)
    html = fig.to_html(full_html=False, include_plotlyjs='cdn',
                       config={'responsive': True, 'scrollZoom': True,
                               'displaylogo': False, 'modeBarButtonsToRemove': ['lasso2d', 'select2d']})
    latest = times.iloc[-1].strftime('%Y/%m/%d %H:%M JST')
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>WTI RCI400 Aurora</title><style>
html,body{{margin:0;height:100%;background:#101829;color:white;font-family:Arial,sans-serif}}
body{{display:flex;flex-direction:column;height:100dvh;overflow:hidden}}
header{{padding:9px 10px;display:flex;align-items:center;justify-content:space-between;font-size:12px}}
button{{background:#344b72;color:white;border:0;border-radius:6px;padding:9px;font-size:13px}}
#plot{{flex:1;min-height:0;overflow:hidden}}#plot .plotly-graph-div{{height:100%!important}}
footer{{padding:7px 10px;color:#b4c7db;font-size:11px;text-align:center}}
</style></head><body>
<header><span>確定足: {latest}</span><button onclick="location.reload()">更新 ↻</button></header>
<div id="plot">{html}</div>
<footer>白線399本・5分足確定値のみ｜黄色=1時間｜青=30分｜左右移動・ピンチ拡大</footer>
<script>
(function(){{
const p=document.getElementById('plot'), g=p.querySelector('.js-plotly-plot');
function resize(){{if(g && window.Plotly)Plotly.relayout(g,{{height:Math.max(250,p.clientHeight)}});}}
if(window.ResizeObserver)new ResizeObserver(resize).observe(p);
window.addEventListener('resize',resize);resize();
// Re-fetch the chart periodically. A reload never changes the MACD400 app.
setInterval(function(){{if(!document.hidden)location.reload();}},300000);
}})();
</script></body></html>'''


@app.get('/')
def home():
    with _lock:
        if _cache['html'] is not None and time.monotonic() - _cache['at'] < 60:
            return Response(_cache['html'], mimetype='text/html')
        try:
            html = make_chart()
            _cache.update(html=html, at=time.monotonic())
            return Response(html, mimetype='text/html')
        except Exception as exc:
            app.logger.exception('RCI400 update failed')
            return Response(f'<h3>RCI400の更新に失敗しました</h3><p>{str(exc)}</p>',
                            status=503, mimetype='text/html')


@app.get('/health')
def health():
    return 'OK'
