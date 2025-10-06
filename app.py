import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io

pd.options.mode.chained_assignment = None

@st.cache_data(ttl=300)  # Cache per reattività, refresh ogni 5 min
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_coingecko_data(days=180):
    url = f"https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days={days}&interval=daily"
    response = requests.get(url)
    if response.status_code != 200:
        st.error("Errore API CoinGecko")
        st.stop()
    data = response.json()
    prices = [point[1] for point in data['prices']]
    dates = [datetime.fromtimestamp(point[0]/1000).date() for point in data['prices']]
    df = pd.DataFrame({'Date': dates, 'Close': prices})
    df.set_index('Date', inplace=True)
    df['Close'] = pd.to_numeric(df['Close'])
    df.index = pd.to_datetime(df.index)
    return df

def get_live_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    response = requests.get(url)
    if response.status_code != 200:
        st.error("Errore API live")
        st.stop()
    return response.json()['bitcoin']['usd']

# Interfaccia Streamlit
st.title("🚀 Analisi RSI con Medie Mobili su Bitcoin")
st.markdown("App reattiva per monitorare RSI(14), SMA e segnali buy/sell su 6 mesi di dati.")

# Sidebar per opzioni
periodo = st.sidebar.selectbox("Periodo dati", [90, 180, 365], index=1)  # Default 6 mesi
if st.sidebar.button("Analizza Ora"):
    with st.spinner("Caricamento dati live..."):
        try:
            df = get_coingecko_data(periodo)
            df['RSI'] = calculate_rsi(df['Close'])
            df = df.dropna()
            
            df['SMA50'] = df['Close'].rolling(window=50).mean()
            df['SMA100'] = df['Close'].rolling(window=100).mean() if len(df) >= 100 else df['Close'].rolling(window=min(50, len(df))).mean()
            
            live_price = get_live_price()
            
            df['oversold'] = df['RSI'] < 30
            df['overbought'] = df['RSI'] > 70
            sma_ref = df['SMA100']
            df['uptrend'] = df['Close'] > sma_ref
            df['downtrend'] = df['Close'] < sma_ref
            
            df['buy_uptrend'] = df['oversold'] & df['uptrend']
            df['sell_downtrend'] = df['overbought'] & df['downtrend']
            df['buy_risky'] = df['oversold'] & df['downtrend']
            df['sell_uptrend'] = df['overbought'] & df['uptrend']
            
            oversold_days = df['oversold'].sum()
            overbought_days = df['overbought'].sum()
            oversold_events = (df['oversold'] != df['oversold'].shift()).cumsum()[df['oversold']].nunique()
            overbought_events = (df['overbought'] != df['overbought'].shift()).cumsum()[df['overbought']].nunique()
            
            buy_uptrend_count = df['buy_uptrend'].sum()
            sell_downtrend_count = df['sell_downtrend'].sum()
            buy_risky_count = df['buy_risky'].sum()
            sell_uptrend_count = df['sell_uptrend'].sum()
            
            df['Month'] = df.index.month
            monthly_summary = df.groupby('Month').agg(
                Oversold_Events=('oversold', lambda x: (x != x.shift()).cumsum()[x].nunique()),
                Overbought_Events=('overbought', lambda x: (x != x.shift()).cumsum()[x].nunique()),
                Buy_Uptrend_Days=('buy_uptrend', 'sum'),
                Sell_Downtrend_Days=('sell_downtrend', 'sum')
            )
            
            interactions = []
            for idx, row in df.iterrows():
                if row['buy_uptrend']:
                    position = "Sopra SMA100" if row['Close'] > row['SMA100'] else "Sotto SMA100"
                    interactions.append({'Data': idx.strftime('%Y-%m-%d'), 'Tipo': 'Buy Uptrend', 'Prezzo': row['Close'], 'RSI': row['RSI'], 'Posizione': position})
                elif row['sell_downtrend']:
                    position = "Sotto SMA100" if row['Close'] < row['SMA100'] else "Sopra SMA100"
                    interactions.append({'Data': idx.strftime('%Y-%m-%d'), 'Tipo': 'Sell Downtrend', 'Prezzo': row['Close'], 'RSI': row['RSI'], 'Posizione': position})
                elif row['buy_risky']:
                    position = "Sotto SMA100" if row['Close'] < row['SMA100'] else "Sopra SMA100"
                    interactions.append({'Data': idx.strftime('%Y-%m-%d'), 'Tipo': 'Buy Risky (Downtrend)', 'Prezzo': row['Close'], 'RSI': row['RSI'], 'Posizione': position})
                elif row['sell_uptrend']:
                    position = "Sopra SMA100" if row['Close'] > row['SMA100'] else "Sotto SMA100"
                    interactions.append({'Data': idx.strftime('%Y-%m-%d'), 'Tipo': 'Sell Uptrend (Pullback)', 'Prezzo': row['Close'], 'RSI': row['RSI'], 'Posizione': position})
            
            interactions_df = pd.DataFrame(interactions) if interactions else pd.DataFrame(columns=['Data', 'Tipo', 'Prezzo', 'RSI', 'Posizione'])
            
            latest = df.iloc[-1]
            current_uptrend = live_price > latest['SMA100']
            current_position = "Sopra SMA100" if live_price > latest['SMA100'] else "Sotto SMA100"
            if latest['RSI'] < 30 and current_uptrend:
                signal = "Buy (Oversold in uptrend)"
            elif latest['RSI'] > 70 and not current_uptrend:
                signal = "Sell (Overbought in downtrend)"
            elif latest['RSI'] > 70:
                signal = "Sell (Possibile pullback in uptrend)"
            else:
                signal = "Hold (Momentum neutro o trend stabile)"
            
            # Output in Streamlit
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Prezzo Live", f"${live_price:,.2f}")
                st.metric("RSI(14) Ultimo", f"{latest['RSI']:.1f}")
                st.metric("Segnale", signal)
                st.metric("Posizione vs SMA100", current_position)
            
            with col2:
                st.metric("Eventi Oversold (<30)", f"{oversold_events} ({oversold_days} gg)")
                st.metric("Eventi Overbought (>70)", f"{overbought_events} ({overbought_days} gg)")
                st.metric("Buy Uptrend Giorni", buy_uptrend_count)
                st.metric("Sell Uptrend Giorni", sell_uptrend_count)
            
            st.subheader("Tabella Mensile")
            st.dataframe(monthly_summary)
            
            st.subheader("Date di Interazioni con Medie")
            if not interactions_df.empty:
                st.dataframe(interactions_df)
            else:
                st.info("Nessuna interazione significativa.")
                
        except Exception as e:
            st.error(f"Errore: {e}")

st.sidebar.markdown("---")
st.sidebar.info("App creata con Streamlit. Dati da CoinGecko API.")