WTI RCI400 Aurora - NEW INDEPENDENT APP

1. Create a NEW GitHub repository (example: wti-rci400). Do not edit wti-aurora.
2. Upload app.py and requirements.txt from this folder to the NEW repository.
3. In Render, create a NEW Web Service from the NEW repository.
4. Build command: pip install -r requirements.txt
5. Start command: gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120
6. Environment variable: SIFTING_API_KEY = the same API key used by MACD400.
7. Open the NEW Render URL. The old MACD400 URL is unchanged.

Caution: Sifting API is assumed to timestamp candles at bar OPEN. This app hides the
current forming 5-minute bar and shows 399 RCI curves (periods 2..400).
The server caches results for 60 seconds; the browser refreshes every 5 minutes.
Check Sifting response format, available data limits, and Render instance performance.
