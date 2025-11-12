import httpx
import xmltodict
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path
from io import BytesIO
import requests
import time

# -------------------------------------------------
# Streamlit config
# -------------------------------------------------
st.set_page_config(page_title="Finans Dashboard", layout="wide")

TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"
BIST_CSV_PATH = Path("us_list.csv")


# -------------------------------------------------
# TCMB FONKSİYONLARI
# -------------------------------------------------
def get_tcmb_data():
    try:
        resp = httpx.get(TCMB_URL, timeout=10)
        resp.raise_for_status()
        data = xmltodict.parse(resp.text)
        currencies = data["Tarih_Date"]["Currency"]

        rows = []
        for c in currencies:
            try:
                rows.append({
                    "Kod": c["@CurrencyCode"],
                    "Ad": c.get("Isim", ""),
                    "Alış": float(c.get("ForexBuying") or 0),
                    "Satış": float(c.get("ForexSelling") or 0),
                })
            except Exception:
                continue
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"TCMB verisi alınamadı: {e}")
        return pd.DataFrame()


def get_past_tcmb_data(currency_code="USD", days=30):
    today = datetime.now()
    all_data = []

    for i in range(days):
        date = today - timedelta(days=i)
        url = f"https://www.tcmb.gov.tr/kurlar/{date.strftime('%Y%m')}/{date.strftime('%d%m%Y')}.xml"
        try:
            resp = httpx.get(url, timeout=5)
            if resp.status_code != 200:
                continue
            data = xmltodict.parse(resp.text)
            currencies = data["Tarih_Date"]["Currency"]
            for c in currencies:
                if c.get("@CurrencyCode") == currency_code:
                    all_data.append({
                        "Tarih": date.strftime("%Y-%m-%d"),
                        "Alış": float(c.get("ForexBuying") or 0),
                        "Satış": float(c.get("ForexSelling") or 0),
                    })
                    break
        except Exception:
            continue

    df = pd.DataFrame(all_data)
    if not df.empty:
        df.sort_values("Tarih", inplace=True)
    return df


def get_investing_bist_data(symbol: str, pair_id: int, days: int = 30):
    """Investing.com üzerinden BIST hissesi için son X günlük veri çeker."""
    try:
        url = f"https://api.investing.com/api/financialdata/historical?pairID={pair_id}&timeFrame=Daily&last={days}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)[["rowDate", "last", "open", "high", "low", "turnover"]]
        df.columns = ["Tarih", "Kapanış", "Açılış", "Yüksek", "Düşük", "Hacim"]
        df["Tarih"] = pd.to_datetime(df["Tarih"])
        df.sort_values("Tarih", inplace=True)
        return df
    except Exception as e:
        st.error(f"Investing verisi alınamadı: {e}")
        return pd.DataFrame()


# -------------------------------------------------
# FINNHUB FONKSİYONU (Fallback)
# -------------------------------------------------
def get_finnhub_bist(symbol):
    """Yahoo çalışmazsa Finnhub'tan BIST verisi çeker."""
    token = st.secrets.get("finnhub_key", None)
    if not token:
        st.error("Finnhub API anahtarı bulunamadı. .streamlit/secrets.toml dosyasına eklemen gerekiyor.")
        return pd.DataFrame()

    url = f"https://finnhub.io/api/v1/quote?symbol=BIST:{symbol.replace('.IS','')}&token={token}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json() or {}

        if not data.get("c"):
            st.warning(f"{symbol} için Finnhub veri döndürmedi.")
            return pd.DataFrame()

        df = pd.DataFrame([{
            "Open": data.get("o", 0),
            "High": data.get("h", 0),
            "Low": data.get("l", 0),
            "Close": data.get("c", 0),
            "Previous Close": data.get("pc", 0),
        }])
        return df

    except Exception as e:
        st.error(f"Finnhub verisi alınamadı: {e}")
        return pd.DataFrame()


# -------------------------------------------------
# BIST LİSTESİ (CSV'DEN)
# -------------------------------------------------
@st.cache_data
def get_all_bist_symbols() -> dict:
    if not BIST_CSV_PATH.exists():
        st.error("bist_list.csv bulunamadı. Proje klasörüne eklediğinden emin ol.")
        return {}

    try:
        df = pd.read_csv(BIST_CSV_PATH)
        if "Kod" not in df.columns or "Ad" not in df.columns:
            st.error("bist_list.csv formatı hatalı. 'Kod' ve 'Ad' kolonları olmalı.")
            return {}
        df = df.dropna(subset=["Kod"])
        return dict(zip(df["Kod"], df["Ad"]))
    except Exception as e:
        st.error(f"bist_list.csv okunamadı: {e}")
        return {}


# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
source = st.sidebar.radio(
    "Veri Kaynağı Seç",
    [
        "TCMB (Döviz)",
        "Son X Günlük Döviz Grafiği",
        "Hisse Arama (Canlı)",
        "Kripto (Canlı)"
    ],
    index=0,
)


# -------------------------------------------------
# ANA BAŞLIK
# -------------------------------------------------
st.title("📊 Finans Dashboard")
st.caption("TCMB ve BIST verilerini tek ekranda gösteren basit dashboard.")


# -------------------------------------------------
# 1️⃣ TCMB
# -------------------------------------------------
if source == "TCMB (Döviz)":
    st.subheader("💰 Güncel Döviz Kurları (TCMB)")
    df = get_tcmb_data()
    if df.empty:
        st.stop()

    st.session_state["tcmb_data"] = df
    st.dataframe(df, use_container_width=True)

    currency = st.selectbox("Detay görmek istediğin para birimi", df["Kod"].tolist(), index=0)
    selected = df[df["Kod"] == currency].iloc[0]

    col3, col4 = st.columns(2)
    col3.metric(label=f"{selected['Ad']} Alış", value=f"{selected['Alış']:.4f}")
    col4.metric(label=f"{selected['Ad']} Satış", value=f"{selected['Satış']:.4f}")

    st.bar_chart(df.set_index("Kod")[["Alış", "Satış"]])


# -------------------------------------------------
# 2️⃣ TCMB — Zaman Serisi
# -------------------------------------------------
elif source == "Son X Günlük Döviz Grafiği":
    st.subheader("📈 Döviz Zaman Serisi (TCMB)")
    df_latest = get_tcmb_data()
    if df_latest.empty:
        st.stop()

    currencies = df_latest["Kod"].tolist()
    selected_currency = st.selectbox("Para Birimi Seç", currencies, index=0)
    selected_days = st.slider("Kaç Günlük Veri Görüntülensin", 7, 60, 30)

    with st.spinner("Veriler çekiliyor..."):
        df_past = get_past_tcmb_data(selected_currency, selected_days)

    if df_past.empty:
        st.warning("Veri bulunamadı. TCMB bazı tarihler için veri yayınlamamış olabilir.")
        st.stop()

    st.session_state["tcmb_data"] = df_past

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_past["Tarih"], y=df_past["Satış"], mode="lines+markers", name="Satış", line=dict(color="orange", width=2)))
    avg_sell = df_past["Satış"].mean()
    fig.add_hline(y=avg_sell, line_dash="dot", line_color="gray", annotation_text=f"Ortalama: {avg_sell:.4f}", annotation_position="top left")
    fig.update_layout(title=f"{selected_currency}/TRY Son {selected_days} Günlük Değişim", xaxis_title="Tarih", yaxis_title="Fiyat (TL)", hovermode="x unified", template="plotly_white", height=500)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df_past, use_container_width=True)


# -------------------------------------------------
# 3️⃣ NASDAQ / NYSE — Finnhub verisi (dinamik CSV'den)
# -------------------------------------------------
# -------------------------------------------------
# 3️⃣ HİSSE ARAMA — Dinamik (Finnhub Search API)
# -------------------------------------------------
elif source == "Hisse Arama (Canlı)":
    st.subheader("🔍 Canlı Hisse Arama (Finnhub)")
    token = st.secrets["finnhub_key"]

    # Kullanıcıdan sembol veya şirket adı
    query = st.text_input("Hisse adı veya sembol gir (örn. AAPL, MSFT, NVDA, AMZN)", "")

    if not query:
        st.info("👆 Aramak istediğin hisse adını veya sembolünü yaz.")
        st.stop()

    try:
        # 🔹 Finnhub'tan sembolleri ara
        with st.spinner("🔎 Hisseler aranıyor..."):
            search_url = f"https://finnhub.io/api/v1/search?q={query}&token={token}"
            results = requests.get(search_url, timeout=10).json().get("result", [])
            if not results:
                st.warning("Sonuç bulunamadı.")
                st.stop()

        options = {r["symbol"]: r.get("description", "") for r in results if r.get("symbol")}
        symbol = st.selectbox(
            "Sonuçlardan birini seç:",
            options=list(options.keys()),
            format_func=lambda x: f"{x} — {options[x]}",
        )

        # 🔹 Anlık fiyat verisini çek
        quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={token}"
        q = requests.get(quote_url, timeout=10).json()

        if not q.get("c"):
            st.warning(f"{symbol} için fiyat verisi bulunamadı.")
            st.stop()

        # 🔹 Veriyi göster
        col1, col2, col3 = st.columns(3)
        change = q["c"] - q["pc"]
        change_pct = (change / q["pc"]) * 100 if q["pc"] else 0
        col1.metric("Son Fiyat", f"${q['c']:.2f}", f"{change:+.2f}")
        col2.metric("Değişim (%)", f"{change_pct:+.2f}%")
        col3.metric("Önceki Kapanış", f"${q['pc']:.2f}")

        # 🔹 Ek bilgi olarak High/Low göster
        col4, col5 = st.columns(2)
        col4.metric("Günün En Yükseği", f"${q['h']:.2f}")
        col5.metric("Günün En Düşüğü", f"${q['l']:.2f}")

        # 🔹 Tek satırlık tablo
        data = pd.DataFrame([{
            "Sembol": symbol,
            "Son Fiyat": q["c"],
            "Önceki Kapanış": q["pc"],
            "En Yüksek": q["h"],
            "En Düşük": q["l"],
            "Değişim": change,
            "Değişim (%)": change_pct
        }])
        st.session_state["stock_data"] = data

        st.dataframe(data.round(2), use_container_width=True)

    except Exception as e:
        st.error(f"Hata: {e}")

# -------------------------------------------------
# 💰 KRİPTO (CANLI)
# -------------------------------------------------
# -------------------------------------------------
# 💰 KRİPTO (CANLI) — Binance API versiyonu
# -------------------------------------------------
elif source == "Kripto (Canlı)":
    st.subheader("💰 Kripto Piyasaları — Binance API Üzerinden (Limitsiz ve Anlık)")

    # Binance'ten USDT paritelerini çek
    @st.cache_data(ttl=3600)
    def get_binance_symbols():
        url = "https://data-api.binance.vision/api/v3/ticker/price"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            # Sadece USDT pariteleri al
            symbols = sorted([d["symbol"] for d in data if d["symbol"].endswith("USDT")])
            return symbols
        except Exception as e:
            st.error(f"Sembol listesi alınamadı: {e}")
            return []

    symbols = get_binance_symbols()
    if not symbols:
        st.stop()

    coin = st.selectbox(
        "Kripto Seç (USDT pariteleri)",
        symbols,
        index=symbols.index("BTCUSDT") if "BTCUSDT" in symbols else 0,
    )

    # Anlık fiyat ve 24 saatlik değişim
    quote_url = f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={coin}"
    try:
        q = requests.get(quote_url, timeout=10).json()
        if "lastPrice" not in q:
            st.warning(f"{coin} için veri bulunamadı.")
            st.stop()

        col1, col2, col3 = st.columns(3)
        last_price = float(q["lastPrice"])
        change = float(q["priceChange"])
        change_pct = float(q["priceChangePercent"])
        prev_close = float(q["prevClosePrice"])
        col1.metric("Son Fiyat", f"${last_price:.4f}", f"{change:+.4f}")
        col2.metric("Değişim (%)", f"{change_pct:+.2f}%")
        col3.metric("Önceki Kapanış", f"${prev_close:.4f}")

        col4, col5 = st.columns(2)
        col4.metric("En Yüksek (24s)", f"${float(q['highPrice']):.4f}")
        col5.metric("En Düşük (24s)", f"${float(q['lowPrice']):.4f}")

        # Son 24 saatlik mum verileri
        import pandas as pd
        from datetime import datetime

        candles_url = f"https://data-api.binance.vision/api/v3/klines?symbol={coin}&interval=15m&limit=96"
        c = requests.get(candles_url, timeout=10).json()

        df = pd.DataFrame(c, columns=[
            "OpenTime", "Open", "High", "Low", "Close", "Volume",
            "CloseTime", "QAV", "Trades", "TBBAV", "TBQAV", "Ignore"
        ])
        df["Tarih"] = pd.to_datetime(df["OpenTime"], unit="ms")
        df["Açılış"] = df["Open"].astype(float)
        df["Kapanış"] = df["Close"].astype(float)
        df["En Yüksek"] = df["High"].astype(float)
        df["En Düşük"] = df["Low"].astype(float)
        df = df[["Tarih", "Açılış", "Kapanış", "En Yüksek", "En Düşük"]]

        # Grafik
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df["Tarih"],
            open=df["Açılış"],
            high=df["En Yüksek"],
            low=df["En Düşük"],
            close=df["Kapanış"],
            name=coin,
            increasing_line_color="limegreen",
            decreasing_line_color="red",
        ))
        fig.update_layout(
            title=f"{coin} — Son 24 Saatlik Fiyat Grafiği (Binance)",
            xaxis_title="Zaman",
            yaxis_title="Fiyat (USD)",
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            height=550,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df.tail(20).round(4), use_container_width=True)
        st.session_state["crypto_data"] = df

    except Exception as e:
        st.error(f"Hata: {e}")

# -------------------------------------------------
# 📤 VERİ DIŞA AKTAR
# -------------------------------------------------
# -------------------------------------------------
# 📤 VERİ DIŞA AKTAR — BIST hariç, Kripto dahil
# -------------------------------------------------
st.markdown("---")
st.header("📤 Veri Dışa Aktar")

dataset_choice = st.selectbox(
    "Veri Seti Seç",
    [
        "💱 TCMB (Döviz Verileri)",
        "📈 Kripto (Binance Verileri)"
    ],
    index=0,
)

export_format = st.radio(
    "İndirme Formatı",
    ["CSV", "JSON", "Excel"],
    index=0,
    horizontal=True,
)

# TCMB ve Kripto verilerini session'dan al
df_tcmb_export = st.session_state.get("tcmb_data", pd.DataFrame())
df_crypto_export = st.session_state.get("crypto_data", pd.DataFrame())

df_export = df_tcmb_export if dataset_choice.startswith("💱") else df_crypto_export

if not df_export.empty:
    st.success(f"{dataset_choice} verisi başarıyla yüklendi. İndirmeye hazırsın 🚀")

    if export_format == "CSV":
        csv = df_export.to_csv(index=False).encode("utf-8")
        st.download_button("📥 CSV olarak indir", csv, "veri.csv", "text/csv")

    elif export_format == "JSON":
        json_data = df_export.to_json(orient="records", indent=2, force_ascii=False)
        st.download_button("📥 JSON olarak indir", json_data, "veri.json", "application/json")

    elif export_format == "Excel":
        buffer = BytesIO()
        df_export.to_excel(buffer, index=False)
        st.download_button(
            "📥 Excel olarak indir",
            buffer.getvalue(),
            "veri.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.warning("Henüz veri çekilmedi. Lütfen önce TCMB veya Kripto sekmesinden veriyi yükle.")
