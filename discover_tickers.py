"""
SmartStock Scanner — IDX Ticker Discovery Script
Discovers all valid Indonesian stock tickers via Yahoo Finance.
Run this once to generate the full ticker cache.

Usage: python discover_tickers.py
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TickerDiscovery")

# Known Indonesian tickers (comprehensive seed list)
# Source: LQ45, IDX80, Kompas100, IDX Pefindo25, IDX SMC Liquid, etc.
SEED_TICKERS = [
    # A
    "AADI","AALI","ABBA","ABDA","ABMM","ACES","ACST","ADES","ADHI","ADIC",
    "ADMF","ADMG","ADMR","ADRO","AGAR","AGII","AGRO","AGRS","AHAP","AIMS",
    "AISA","AKKU","AKPI","AKRA","AKSI","ALDO","ALKA","ALMI","ALTO","AMAR",
    "AMFG","AMIN","AMMN","AMRT","ANDI","ANJT","ANTM","APEX","APII","APLI",
    "APLN","ARCI","ARGO","ARII","ARKA","ARMY","ARNA","ARTO","ASBI","ASGR",
    "ASII","ASLC","ASMI","ASRI","ASRM","ASSA","ATAP","AUTO","AVIA",
    # B
    "BACA","BAJA","BALI","BANK","BAPA","BATA","BAUT","BBCA","BBHI","BBKP",
    "BBLD","BBMD","BBNI","BBRI","BBRM","BBSI","BBSS","BBTN","BBYB","BCAP",
    "BCIC","BCIP","BDKR","BDMN","BEEF","BELL","BELI","BEST","BFIN","BGTG",
    "BHAT","BHIT","BIKA","BINA","BIRD","BISI","BJBR","BJTM","BKDP","BKSL",
    "BLTA","BLTZ","BLUE","BMAS","BMHS","BMRI","BMSR","BMTR","BNBA","BNBR",
    "BNGA","BNII","BNLI","BOBA","BOLT","BOMB","BORN","BOSS","BPII","BRAM",
    "BREN","BRIS","BRMS","BRNA","BRPT","BSDE","BSGR","BSIM","BSML","BSSR",
    "BTEK","BTPN","BTPS","BUDI","BUKA","BULL","BUMI","BVIC","BWPT",
    # C
    "CAMP","CARE","CARS","CASA","CASH","CASS","CBMF","CCSI","CEKA","CENT",
    "CFIN","CINT","CITA","CITY","CLEO","CLPI","CMNP","CMNT","CMPP","CMRY",
    "CNKO","CNTX","COAL","COCO","CONB","COSS","COWL","CPGT","CPIN","CPRI",
    "CPRO","CRAB","CSAP","CSIS","CSMI","CSRA","CTRA","CTTH","CUAN",
    # D
    "DADO","DADA","DART","DAYA","DCII","DEAL","DEFI","DEWA","DFAM","DILD",
    "DIVA","DKFT","DLTA","DMAS","DMMX","DNAR","DNET","DOID","DPNS","DPUM",
    "DRMA","DSFI","DSNG","DSSA","DUCK","DUTI","DVLA","DWGL","DYAN",
    # E
    "EAST","ECII","EDGE","EKAD","ELSA","ELTY","EMDE","EMTK","ENRG","ENVY",
    "EPMT","ERAA","ERTX","ESIP","ESSA","ESTA","ESTI","EURO","EVEN","EXCL",
    # F
    "FAPA","FAST","FASW","FILM","FIMP","FIRE","FISH","FITT","FLMC","FMII",
    "FOOD","FORU","FPNI","FREN","FUJI","FUTR",
    # G
    "GAMA","GDST","GDYR","GEMA","GEMS","GGRM","GGRP","GHON","GJTL","GLOB",
    "GLVA","GMFI","GMTD","GOLD","GOTO","GPRA","GRIA","GSMF","GTBO","GTSI",
    "GZCO",
    # H
    "HADE","HALL","HAIS","HDFA","HDIT","HDTX","HEAL","HELI","HERO","HEXA",
    "HITS","HKMU","HMSP","HOKI","HOME","HOPE","HOTL","HRME","HRTA","HRUM",
    "HUBG",
    # I
    "IATA","IBFN","IBST","ICBP","ICON","IDEA","IDPR","IFII","IFSH","IGAR",
    "IIKP","IKAI","IMAS","IMJS","IMPC","INAF","INAI","INCO","INDF","INDR",
    "INDS","INDX","INDY","INKP","INPC","INPP","INPS","INRU","INTA","INTD",
    "INTP","IPCC","IPOL","IPTV","ISAT","ISSP","ITMG","ITMA",
    # J
    "JARR","JAWA","JAYA","JGLE","JIHD","JKON","JMAS","JPFA","JRPT","JSKY",
    "JSMR","JTPE",
    # K
    "KAEF","KARW","KBAG","KBLI","KBLM","KBLV","KDSI","KEEN","KEJU","KIAS",
    "KICI","KIJA","KINO","KIOS","KJEN","KLBF","KMTR","KONI","KOPI","KOTA",
    "KPAL","KPAS","KPIG","KRAS","KREN","KRYA",
    # L
    "LABA","LAND","LAPD","LCGP","LEAD","LIFE","LINK","LION","LMAS","LMPI",
    "LMSH","LPCK","LPGI","LPIN","LPKR","LPLI","LPPF","LPPS","LSIP","LTLS",
    "LUCK","LUMI",
    # M
    "MAHA","MAIN","MAMI","MANG","MAPA","MAPI","MARK","MASA","MAYA","MBAP",
    "MBMA","MBSS","MBTO","MCAS","MCOL","MDIA","MDKA","MDKI","MDLN","MEDC",
    "MEGA","MERK","META","MFIN","MFMI","MGRO","MICI","MIDI","MIKA","MINA",
    "MIRA","MKNT","MKPI","MLBI","MLIA","MLPL","MLPT","MMLP","MNCN","MOLI",
    "MPMX","MPOW","MPPA","MPRO","MRAT","MREI","MRSN","MSIN","MSKY","MTEL",
    "MTDL","MTFN","MTLA","MTMH","MTSM","MTWI","MYOH",
    # N
    "NAGA","NANO","NATO","NCKL","NELY","NETV","NICK","NICL","NIKL","NINE",
    "NISP","NOBU","NPGF","NRCA","NUSA",
    # O
    "OASA","OBMD","OCAP","OILS","OKAS","OMRE","OPMS","OTIC",
    # P
    "PACK","PADI","PALM","PAMG","PANI","PANR","PANS","PBID","PBRX","PCAR",
    "PDES","PEGA","PEHA","PGAS","PGEO","PGLI","PGRS","PGUN","PJAA","PKPK",
    "PLAN","PLIN","PMJS","PMMP","PNBN","PNBS","PNGO","PNIN","PNLF","PNSE",
    "POLA","POLI","POLL","POLY","POOL","PORT","POWR","PPGL","PPRE","PPRI",
    "PPRO","PRAS","PRDA","PRIM","PSAB","PSDN","PSGO","PTBA","PTIS","PTMP",
    "PTPP","PTPW","PTRO","PTSP","PUDP","PURA","PURI","PWON","PYFA",
    # R
    "RAJA","RALS","RANC","RBMS","RDTX","REAL","RELI","RICY","RIGS","RIMO",
    "RISE","RMBA","RMKE","ROCK","RODA","RONY","ROTI","RSGK","RUIS",
    # S
    "SAFE","SAGE","SAME","SAPX","SATU","SBAT","SBMA","SCCO","SCMA","SCNP",
    "SDMU","SDPC","SDRA","SEMA","SFAS","SGER","SGRO","SHID","SHIP","SIDE",
    "SICO","SIDO","SILO","SIMA","SIMP","SINI","SIPD","SKBM","SKLT","SKRN",
    "SLIS","SMCB","SMDM","SMDR","SMGR","SMKL","SMMA","SMMT","SMSM","SMRA",
    "SMSM","SNLK","SOCI","SOFA","SOHO","SONA","SOUL","SOSS","SPMA","SPTO",
    "SQMI","SRAJ","SRIL","SRSN","SRTG","SSMS","SSIA","SSII","SSTM","STAR",
    "STTP","STAA","SULI","SUPR","SURE","SWAT",
    # T
    "TALF","TAMA","TAMU","TANI","TAPG","TARA","TAXI","TBIG","TBLA","TBMS",
    "TCID","TCPI","TDPM","TEBE","TECH","TELE","TFAS","TGKA","TGRA","TIFA",
    "TINS","TIRA","TIRT","TKIM","TLKM","TMAS","TMPO","TNCA","TOBA","TOPS",
    "TOTL","TOTO","TOWR","TOYS","TPIA","TPMA","TRJA","TRIM","TRIS","TRST",
    "TRUE","TRUK","TSPC","TUGU","TURI",
    # U
    "UANG","UBSI","UCID","UFOE","ULTJ","UNIC","UNIT","UNSP","UNTR","UNVR",
    "URBN","UVCR",
    # V
    "VICI","VICO","VINS","VIVA","VKTR","VRNA",
    # W
    "WAPO","WEGE","WEHA","WGSH","WICO","WIFI","WIIM","WIKA","WINS","WMPP",
    "WMUU","WOOD","WOWS","WSBP","WSKT","WTON",
    # X-Z
    "YELO","YULE","ZBRA","ZONE","ZYRX",
]


def discover_valid_tickers(seed_list: list[str], batch_size: int = 50) -> list[str]:
    """
    Test all seed tickers against Yahoo Finance in batches.
    Returns list of valid (active) tickers.
    """
    valid_tickers = set()
    total = len(seed_list)

    for i in range(0, total, batch_size):
        batch = seed_list[i:i + batch_size]
        jk_batch = [f"{t}.JK" for t in batch]
        batch_str = " ".join(jk_batch)

        try:
            data = yf.download(batch_str, period="1d", progress=False, threads=True)
            if not data.empty and isinstance(data.columns, pd.MultiIndex):
                found = set(c.replace(".JK", "") for c in data.columns.get_level_values(1))
                # Filter out tickers with all NaN close prices
                for ticker in found:
                    col = ("Close", f"{ticker}.JK")
                    if col in data.columns and data[col].notna().any():
                        valid_tickers.add(ticker)

            progress = min(i + batch_size, total)
            logger.info(f"Progress: {progress}/{total} tested, {len(valid_tickers)} valid so far")

        except Exception as e:
            logger.error(f"Batch {i}-{i+batch_size} error: {e}")

        time.sleep(0.2)  # Small delay between batches

    return sorted(valid_tickers)


def main():
    logger.info(f"Starting ticker discovery with {len(SEED_TICKERS)} seed tickers...")

    valid = discover_valid_tickers(SEED_TICKERS)

    logger.info(f"\n{'='*50}")
    logger.info(f"Discovery complete: {len(valid)} valid tickers found")

    # Save to cache
    cache_file = Path("cache/idx_tickers.json")
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    cache_data = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "count": len(valid),
        "source": "yfinance_discovery",
        "tickers": valid,
    }

    with open(cache_file, "w") as f:
        json.dump(cache_data, f, indent=2)

    logger.info(f"Saved {len(valid)} tickers to {cache_file}")
    print(f"\n✅ Done! {len(valid)} valid IDX tickers saved to {cache_file}")


if __name__ == "__main__":
    main()
