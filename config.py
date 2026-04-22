"""
SmartStock Scanner — Configuration & Constants
Ensemble-Kalman Edition
"""

# ──────────────────────────────────────────────
# IDX Most Liquid Stocks (~200 tickers)
# Sources: LQ45, IDX80, Kompas100, IDX High Dividend
# ──────────────────────────────────────────────
IDX_TICKERS = [
    # === LQ45 Core ===
    "ACES", "ADRO", "AKRA", "AMMN", "AMRT",
    "ANTM", "ASII", "BBCA", "BBNI", "BBRI",
    "BBTN", "BMRI", "BREN", "BRPT", "BUKA",
    "CPIN", "EMTK", "ESSA", "EXCL", "GOTO",
    "GGRM", "HRUM", "ICBP", "INCO", "INDF",
    "INKP", "ITMG", "JPFA", "KLBF", "MAPI",
    "MDKA", "MEDC", "MIKA", "PGAS", "PGEO",
    "PTBA", "SMGR", "TBIG", "TINS", "TLKM",
    "TOWR", "UNTR", "UNVR", "WMUU",
    # === IDX80 Extended ===
    "AALI", "AGII", "ARTO", "BBKP", "BFIN",
    "BGTG", "BJBR", "BRIS", "BTPS", "BSDE",
    "CMRY", "DNET", "DSNG", "ELSA", "ERAA",
    "FILM", "HEAL", "HMSP", "HOKI", "INDY",
    "ISAT", "JSMR", "LPPF", "MAPA", "MBMA",
    "MCOL", "MKPI", "MNCN", "MTEL", "NISP",
    "PANI", "PEHA", "PGRS", "PNBN", "PTPP",
    "PWON", "SCMA", "SIDO", "SILO", "SMRA",
    "SRTG", "TAPG", "TKIM", "TPIA", "TSPC",
    "WIKA", "WSBP",
    # === Kompas100 & Others ===
    "AADI", "ADIC", "ADMR", "AGRO", "AHAP",
    "AIMS", "ALTO", "AMAR", "APEX", "APLN",
    "ASRI", "ASSA", "AUTO", "BALI", "BANK",
    "BBYB", "BCAP", "BDMN", "BEST", "BIRD",
    "BMHS", "BMTR", "BORN", "BPII", "BRIS",
    "BSML", "BTPN", "BULL", "CLEO", "CPRO",
    "CTRA", "DEWA", "DILD", "DMAS", "DOID",
    "DSNG", "DWGL", "EAST", "EDGE", "EMDE",
    "ENRG", "EPMT", "FAST", "FIRE", "GJTL",
    "GMFI", "GOLD", "GZCO", "HDFA", "HEXA",
    "HITS", "HRTA", "IBFN", "IMJS", "INPC",
    "INTP", "IPOL", "IPTV", "ISSP", "JARR",
    "JSKY", "KEEN", "KINO", "KIOS", "KRAS",
    "LEAD", "LINK", "LPKR", "LSIP", "MAIN",
    "MARK", "MAYA", "META", "MGRO", "MIDI",
    "MLBI", "MLPL", "MMLP", "MOLI", "MPPA",
    "MSIN", "MTDL", "MTLA", "MYOH", "NCKL",
    "NICK", "NIKL", "NPGF", "OASA", "PBRX",
    "PGAS", "PJAA", "PNLF", "PNSE", "PPRE",
    "PSAB", "PTRO", "PTSP", "RAJA", "RANC",
    "ROTI", "SGER", "SKBM", "SMMA", "SMSM",
    "SSIA", "SSMS", "SULI", "TARA", "TAXI",
    "TBLA", "TCPI", "TELE", "TGKA", "TOBA",
    "TOPS", "TOTL", "TRJA", "ULTJ", "UVCR",
    "VINS", "VRNA", "WEGE", "WIFI", "WOOD",
    "WSKT", "WTON",
]

# ──────────────────────────────────────────────
# Scoring Thresholds (per trade type)
# ──────────────────────────────────────────────
SCORE_BUY_THRESHOLD = 35           # Default minimum score for BUY signal
SCORE_STRONG_SIGNAL = 55           # Score >= 55 = "Strong Signal"

# Per-type thresholds (override default)
THRESHOLD_DAY_TRADING = 30         # Day trading: more aggressive entry
THRESHOLD_BSJP = 30                # BSJP: momentum-based, lower bar
THRESHOLD_SWING = 35               # Swing: slightly more conservative

# Max score per layer
KALMAN_MAX_SCORE = 30
INDICATOR_MAX_SCORE = 30
VOLUME_PATTERN_MAX_SCORE = 40

# ──────────────────────────────────────────────
# Risk Management
# ──────────────────────────────────────────────
MAX_RISK_PERCENT = 2.0             # Maximum allowed risk per trade (2% Rule)
DEFAULT_TP_RATIO = 2.0             # Risk:Reward ratio (1:2 default)

# ──────────────────────────────────────────────
# Technical Indicator Parameters
# ──────────────────────────────────────────────
MA_SHORT_PERIOD = 20               # Short-term Moving Average
MA_LONG_PERIOD = 200               # Major trend Moving Average
RSI_PERIOD = 14                    # RSI lookback period
RSI_OVERSOLD = 30                  # RSI oversold threshold
RSI_OVERBOUGHT = 70                # RSI overbought threshold
BB_PERIOD = 20                     # Bollinger Bands period
BB_STD = 2                         # Bollinger Bands standard deviation

# ──────────────────────────────────────────────
# Volume Parameters
# ──────────────────────────────────────────────
VOLUME_SPIKE_MULTIPLIER = 1.5      # Volume > 1.5x avg = spike
VBP_BINS = 20                      # Number of price bins for VBP

# ──────────────────────────────────────────────
# Data Fetching
# ──────────────────────────────────────────────
DATA_PERIOD = "3mo"                # Historical data period
DATA_INTERVAL = "1d"               # Data granularity
INTRADAY_PERIOD = "5d"             # For intraday VWAP
INTRADAY_INTERVAL = "15m"          # 15-minute bars for intraday

# ──────────────────────────────────────────────
# Schedule (WIB / UTC+7)
# ──────────────────────────────────────────────
MARKET_OPEN_HOUR = 9               # 09:00 WIB
MARKET_OPEN_MINUTE = 0
MARKET_CLOSE_HOUR = 15             # 15:00 WIB (Pre-close)
MARKET_CLOSE_MINUTE = 0
SCAN_INTERVAL_MINUTES = 15         # Scan every 15 minutes

# ──────────────────────────────────────────────
# Trade Types
# ──────────────────────────────────────────────
TRADE_TYPE_DAY = "Day Trading"
TRADE_TYPE_BSJP = "BSJP"
TRADE_TYPE_SWING = "Swing Trading"
