Logic Engine: Stock Screener (BSJP & Swing)
1. Konstanta & Input Data

Data Requirements: * OHLCV (Open, High, Low, Close, Volume) harian.

    Periode lookback: Minimum 60 hari bursa.

2. Algoritma I: Day Trading (BSJP Momentum)

Tujuan: Mencari "Closing Strength" (kekuatan penutupan) untuk exit di pembukaan besok.
A. Perhitungan Indikator (Technical Indicators)

    EMA 5 & EMA 20: EMAt​=(Pricet​×α)+(EMAt−1​×(1−α))

    RSI (14): Relative Strength Index standar.

    Volume Ratio: Vol_Ratio=SMA(Volume,20)Volumetoday​​

    Relative Close (RC): Skor posisi harga tutup dalam rentang harian.
    RC=High−LowClose−Low​

B. Filter Logika (Entry Criteria)

Sebuah ticker dinyatakan "VALID BSJP" jika memenuhi semua kondisi berikut:

    Trend: Close>EMA5​ AND EMA5​>EMA20​

    Strength: 55≤RSI≤72

    Volume: Vol_Ratio≥1.5 (Konfirmasi partisipasi besar)

    Price Action: RC≥0.8 (Tutup di 20% area teratas rentang harian)

3. Algoritma II: Swing Trading (Trend Following)

Tujuan: Menangkap awal gelombang naik (rebound atau breakout) untuk durasi 3-14 hari.
A. Perhitungan Indikator

    SMA 20 & SMA 50: Simple Moving Average.

    MACD: (EMA12​−EMA26​) sebagai MACD Line, dan EMA9​ dari MACD Line sebagai Signal Line.

    Stochastic Oscillator (14, 3, 3): Nilai %K dan %D.

B. Filter Logika (Entry Criteria)

Sebuah ticker dinyatakan "VALID SWING" jika memenuhi salah satu kondisi setup berikut:

Setup A: The Golden Cross (Trend Reversal)

    SMA20​ memotong ke atas SMA50​ dalam 3 hari terakhir.

    Close>SMA20​

Setup B: Momentum Shift (MACD)

    MACD_Line>Signal_Line

    Histogramtoday​>Histogramyesterday​ (Akselerasi momentum)

    Stochastic %K<40 (Baru mulai naik dari area bawah)

4. Algoritma III: Risk Management (Profitability Check)

Setiap sinyal yang lolos filter di atas wajib dihitung nilai ekonomisnya:
A. Perhitungan Support & Resistance

    Support (S): Nilai terendah (Low) dari 5 hari terakhir.

    Resistance (R): Nilai tertinggi (High) dari 20 hari terakhir.

B. Risk/Reward Ratio (RRR)
RRR=Stop Loss (Close−S)Target Profit (R−Close)​

Kriteria Lolos:

    Hanya tampilkan sinyal jika RRR≥2.0.