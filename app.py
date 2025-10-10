import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

pd.options.mode.chained_assignment = None

@st.cache_data(ttl=300)  # Cache per reattività
def calculate_rsi(prices, period=9):  # RSI(9)
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_coingecko_data(days=180, crypto_id='bitcoin'):
    url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
    response = requests.get(url)
    if response.status_code != 200:
        st.error(f"Errore API CoinGecko per {crypto_id}")
        st.stop()
    data = response.json()
    prices = [point[1] for point in data['prices']]
    dates = [datetime.fromtimestamp(point[0]/1000).date() for point in data['prices']]
    df = pd.DataFrame({'Date': dates, 'Close': prices})
    df.set_index('Date', inplace=True)
    df['Close'] = pd.to_numeric(df['Close'])
    df.index = pd.to_datetime(df.index)
    return df

def get_live_price(crypto_id='bitcoin'):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd"
    response = requests.get(url)
    if response.status_code != 200:
        st.error(f"Errore API live per {crypto_id}")
        st.stop()
    return response.json()[crypto_id]['usd']

# Mappa ticker a ID CoinGecko
TICKER_MAP = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'SOL': 'solana',
    'ADA': 'cardano',
    'DOT': 'polkadot',
    'BNB': 'binancecoin'
}

# Titolo e Intro (sempre visibile)
st.title("🚀 Analisi RSI con Medie Mobili su Crypto")
st.markdown("App gratuita per monitorare RSI(9), SMA e segnali buy/sell su BTC, ETH, SOL, ADA, DOT e BNB. Seleziona un ticker e analizza!")

# Sidebar per opzioni
ticker_symbol = st.sidebar.selectbox("Seleziona Ticker Crypto", list(TICKER_MAP.keys()), index=0)
crypto_id = TICKER_MAP[ticker_symbol]
periodo = st.sidebar.selectbox("Periodo dati (giorni)", [90, 180, 365], index=1)

# Bottone per pulire cache
if st.sidebar.button("Pulisci Cache"):
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("Analizza Ora"):
    with st.spinner(f"Caricamento dati live per {ticker_symbol}..."):
        try:
            df = get_coingecko_data(periodo, crypto_id)
            df['RSI'] = calculate_rsi(df['Close']).round(2)
            df = df.dropna()
            
            df['SMA50'] = df['Close'].rolling(window=50).mean()
            df['SMA100'] = df['Close'].rolling(window=100).mean() if len(df) >= 100 else df['Close'].rolling(window=min(50, len(df))).mean()
            
            # Pulizia NaN per SMA
            df = df.dropna(subset=['SMA100'])
            
            live_price = get_live_price(crypto_id)
            
            df['oversold'] = df['RSI'] < 30
            df['overbought'] = df['RSI'] > 70
            df['extreme_oversold'] = df['RSI'] < 20  # Nuova condizione per RSI < 20
            df['extreme_overbought'] = df['RSI'] > 80  # Nuova condizione per RSI > 80
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
            extreme_oversold_days = df['extreme_oversold'].sum()
            extreme_overbought_days = df['extreme_overbought'].sum()
            
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
                rsi_val = round(row['RSI'], 2)
                if row['buy_uptrend']:
                    position = "Sopra SMA100" if row['Close'] > row['SMA100'] else "Sotto SMA100"
                    interactions.append({'Data': idx.strftime('%Y-%m-%d'), 'Tipo': 'Buy Uptrend', 'Prezzo': row['Close'], 'RSI': rsi_val, 'Posizione': position})
                elif row['sell_downtrend']:
                    position = "Sotto SMA100" if row['Close'] < row['SMA100'] else "Sopra SMA100"
                    interactions.append({'Data': idx.strftime('%Y-%m-%d'), 'Tipo': 'Sell Downtrend', 'Prezzo': row['Close'], 'RSI': rsi_val, 'Posizione': position})
                elif row['buy_risky']:
                    position = "Sotto SMA100" if row['Close'] < row['SMA100'] else "Sopra SMA100"
                    interactions.append({'Data': idx.strftime('%Y-%m-%d'), 'Tipo': 'Buy Risky (Downtrend)', 'Prezzo': row['Close'], 'RSI': rsi_val, 'Posizione': position})
                elif row['sell_uptrend']:
                    position = "Sopra SMA100" if row['Close'] > row['SMA100'] else "Sotto SMA100"
                    interactions.append({'Data': idx.strftime('%Y-%m-%d'), 'Tipo': 'Sell Uptrend (Pullback)', 'Prezzo': row['Close'], 'RSI': rsi_val, 'Posizione': position})
            
            interactions_df = pd.DataFrame(interactions) if interactions else pd.DataFrame(columns=['Data', 'Tipo', 'Prezzo', 'RSI', 'Posizione'])
            
            # Debug: Mostra numero interazioni
            st.info(f"Trovate {len(interactions_df)} interazioni medie nel periodo.")
            
            latest = df.iloc[-1]
            latest_rsi = round(latest['RSI'], 2)
            current_uptrend = live_price > latest['SMA100']
            current_position = "Sopra SMA100" if live_price > latest['SMA100'] else "Sotto SMA100"
            if latest_rsi < 30 and current_uptrend:
                signal = "Buy (Oversold in uptrend)"
            elif latest_rsi > 70 and not current_uptrend:
                signal = "Sell (Overbought in downtrend)"
            elif latest_rsi > 70:
                signal = "Sell (Possibile pullback in uptrend)"
            else:
                signal = "Hold (Momentum neutro o trend stabile)"
            
            # Output
            col1, col2 = st.columns(2)
            with col1:
                st.metric(f"Prezzo Live {ticker_symbol}", f"${live_price:,.2f}")
                st.metric("RSI(9) Ultimo", f"{latest_rsi}")
                st.metric("Segnale", signal)
                st.metric("Posizione vs SMA100", current_position)
            
            with col2:
                st.metric("Eventi Oversold (<30)", f"{oversold_events} ({oversold_days} gg)")
                st.metric("Eventi Overbought (>70)", f"{overbought_events} ({overbought_days} gg)")
                st.metric("Buy Uptrend Giorni", buy_uptrend_count)
                st.metric("Sell Uptrend Giorni", sell_uptrend_count)
            
            st.subheader("Tabella Mensile")
            st.dataframe(monthly_summary)
            
            # Tabella per Oversold (RSI < 30)
            st.subheader("Date Eventi Oversold (RSI < 30)")
            oversold_events_df = df[df['oversold']][['RSI', 'Close']].round(2).reset_index()
            oversold_events_df['Data'] = oversold_events_df['Date'].dt.strftime('%Y-%m-%d')
            oversold_events_df = oversold_events_df[['Data', 'RSI', 'Close']]
            oversold_events_df.columns = ['Data', 'RSI', 'Prezzo']
            if not oversold_events_df.empty:
                st.dataframe(oversold_events_df)
            else:
                st.info("Nessun evento oversold (RSI < 30) nel periodo.")
            
            # Tabella per Overbought (RSI > 70)
            st.subheader("Date Eventi Overbought (RSI > 70)")
            overbought_events_df = df[df['overbought']][['RSI', 'Close']].round(2).reset_index()
            overbought_events_df['Data'] = overbought_events_df['Date'].dt.strftime('%Y-%m-%d')
            overbought_events_df = overbought_events_df[['Data', 'RSI', 'Close']]
            overbought_events_df.columns = ['Data', 'RSI', 'Prezzo']
            if not overbought_events_df.empty:
                st.dataframe(overbought_events_df)
            else:
                st.info("Nessun evento overbought (RSI > 70) nel periodo.")
            
            # Nuova tabella per Prezzi Triggering Estremi (RSI < 20 e RSI > 80)
            st.subheader("Prezzi Triggering Estremi (RSI < 20 e RSI > 80)")
            extreme_events_df = df[df['extreme_oversold'] | df['extreme_overbought']][['RSI', 'Close']].round(2).reset_index()
            extreme_events_df['Data'] = extreme_events_df['Date'].dt.strftime('%Y-%m-%d')
            extreme_events_df['Tipo'] = extreme_events_df['RSI'].apply(lambda x: 'Extreme Oversold' if x < 20 else 'Extreme Overbought')
            extreme_events_df = extreme_events_df[['Data', 'RSI', 'Close', 'Tipo']]
            extreme_events_df.columns = ['Data', 'RSI', 'Prezzo', 'Tipo']
            if not extreme_events_df.empty:
                st.dataframe(extreme_events_df)
                st.info(f"Trovati {len(extreme_events_df)} eventi estremi: {extreme_oversold_days} giorni RSI < 20, {extreme_overbought_days} giorni RSI > 80.")
            else:
                st.warning("Nessun evento estremo (RSI < 20 o RSI > 80) nel periodo. Prova un periodo più lungo o ticker più volatile.")
            
            # Tabella per Interazioni con Medie
            st.subheader(f"Date di Interazioni con Medie per {ticker_symbol}")
            if not interactions_df.empty:
                last_interaction = interactions_df.tail(1)
                if not last_interaction.empty:
                    st.info(f"RSI per ultima interazione (oggi): {last_interaction['RSI'].iloc[0]} – Coerente con metrica principale.")
                st.dataframe(interactions_df)
            else:
                st.warning("Nessuna interazione significativa nel periodo. Prova un periodo più lungo o ticker diverso.")
                
        except Exception as e:
            st.error(f"Errore: {e}")

st.sidebar.markdown("---")
st.sidebar.info("App gratuita creata con Streamlit. Dati da CoinGecko API.")