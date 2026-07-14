#!/usr/bin/env python3
"""
ATLAS — Shiller-data (CAPE, Excess CAPE Yield, reele koers, totaalrendement).

Bron: https://shillerdata.com  ->  ie_data.xls

TWEE VALKUILEN IN DAT BESTAND, allebei hier opgelost:

1. DE KOLOMNAMEN LIEGEN.
   Het blad heeft een samengevoegde koptekst "Real" boven een blok kolommen.
   Pandas ziet die kop niet en nummert dubbele namen gewoon door:
       'Date', 'P', 'D', 'E', 'CPI', 'Fraction', 'Rate GS10',
       'Price', 'Dividend', 'Price.1', 'Earnings', ...
   waarbij:
       'P'        = de NOMINALE koers
       'Price'    = de REELE koers          <- heet dus NIET "Real Price"
       'Dividend' = het REELE dividend
       'Price.1'  = de REELE TOTAALRENDEMENTSINDEX (koers + herbelegd dividend)
   Zoeken op "real price" vindt niets. Zoeken op "price" pakt een kolom die AL
   reeel is en deelt hem nog eens door de CPI -> een reeks vol NaN, en dus nul
   gedateerde crashes.

2. DE DATUM IS EEN GETAL, GEEN DATUM.
   1871.01 = januari 1871. Maar 1871.1 = OKTOBER 1871, niet januari - Excel laat
   de nul weg. Numeriek rekenen lost dat op: (1871.1 - 1871) * 100 = 10.
   Sommige rijen (voetnoten, lege regels) hebben helemaal geen geldige datum.
   Die gooien we weg in plaats van erop vast te lopen.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path("shiller_cache.pkl")
LOCAL = ["ie_data.xls", "ie_data.xlsx", "shiller.csv", "shiller.xls"]
URLS = ["https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/"
        "downloads/ie_data.xls"]


def _parse_date(v):
    """1871.01 -> jan 1871.  1871.1 -> OKT 1871 (Excel laat de nul weg)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):        # lege cellen worden NaN, en int(NaN) klapt
        return None
    year = int(f)
    if not (1800 < year < 2200):
        return None
    month = int(round((f - year) * 100))
    if not (1 <= month <= 12):
        return None
    return pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)


def _read_any(source) -> pd.DataFrame:
    if str(source).endswith(".csv"):
        return pd.read_csv(source)
    return pd.read_excel(source, sheet_name="Data", skiprows=7)


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    raw = list(df.columns)
    lower = {str(c).strip().lower(): c for c in raw}

    def find(*keys, exclude=()):
        for want in keys:
            for low, orig in lower.items():
                if want in low and not any(x in low for x in exclude):
                    return orig
        return None

    c_date = find("date")
    c_cape = find("cape", "p/e10", "pe10")
    c_rate = find("long interest rate", "rate gs10", "gs10")
    c_cpi = find("cpi", "consumer price")

    if c_date is None or c_cape is None:
        raise ValueError(f"Shiller-kolommen niet herkend: {raw[:15]}")

    out = pd.DataFrame(index=df.index)
    out["date"] = df[c_date].map(_parse_date)
    out["cape"] = pd.to_numeric(df[c_cape], errors="coerce")
    out["rate"] = pd.to_numeric(df[c_rate], errors="coerce") if c_rate else np.nan
    out["cpi"] = pd.to_numeric(df[c_cpi], errors="coerce") if c_cpi else np.nan

    if "Price.1" in raw and "P" in raw:            # het echte Shiller-blad
        out["realprice"] = pd.to_numeric(df["Price"], errors="coerce")
        out["realdiv"] = pd.to_numeric(df["Dividend"], errors="coerce")
        out["realtr"] = pd.to_numeric(df["Price.1"], errors="coerce")
    else:                                          # andere bron, bijv. losse CSV
        c_real = find("real price")
        c_nom = find("price", exclude=("real", "consumer"))
        if c_real:
            out["realprice"] = pd.to_numeric(df[c_real], errors="coerce")
        elif c_nom and c_cpi:
            p = pd.to_numeric(df[c_nom], errors="coerce")
            c = pd.to_numeric(df[c_cpi], errors="coerce")
            base = c.dropna().iloc[-1] if c.notna().any() else np.nan
            out["realprice"] = p / c * base
        else:
            out["realprice"] = np.nan
        c_rdiv = find("real dividend")
        out["realdiv"] = (pd.to_numeric(df[c_rdiv], errors="coerce")
                          if c_rdiv else np.nan)
        out["realtr"] = np.nan

    out = out.dropna(subset=["date"])
    return out.set_index("date").sort_index()


def load_shiller(verbose: bool = True) -> pd.DataFrame:
    if CACHE.exists():
        return pd.read_pickle(CACHE)

    for p in LOCAL:                                # lokaal bestand gaat voor
        if Path(p).exists():
            df = _normalise(_read_any(p))
            if verbose:
                print(f"  Shiller gelezen uit lokaal bestand: {p}")
            df.to_pickle(CACHE)
            return df

    import requests                                # anders proberen te downloaden
    for url in URLS:
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "ATLAS/1.0"})
            r.raise_for_status()
            df = _normalise(_read_any(io.BytesIO(r.content)))
            if verbose:
                print("  Shiller gedownload.")
            df.to_pickle(CACHE)
            return df
        except Exception:
            continue

    raise RuntimeError("Shiller-data niet gevonden. Download ie_data.xls van "
                       "shillerdata.com en zet het in deze map.")


def shiller_series(name: str) -> pd.Series:
    df = load_shiller(verbose=False)

    if name == "CAPE":
        return df["cape"].dropna()

    if name == "REALPRICE":
        return df["realprice"].dropna()

    if name == "REALTR":
        if df["realtr"].notna().any():             # Shiller levert hem zelf
            return df["realtr"].dropna()
        p, d = df["realprice"], df["realdiv"]      # anders zelf opbouwen
        if d.isna().all():
            return p.dropna()
        r = (p + d / 12) / p.shift(1) - 1
        return (1 + r.fillna(0)).cumprod().dropna()

    if name == "ECY":
        # Excess CAPE Yield: het omgekeerde van CAPE, min de REELE 10-jaarsrente.
        # Meet of aandelen duur zijn TEN OPZICHTE VAN obligaties - een andere
        # vraag dan of ze absoluut duur zijn. In 2000 diep negatief; in 2009
        # juist ruim positief, terwijl CAPE toen nog altijd niet laag was.
        cape_yield = 100.0 / df["cape"]
        infl10 = (df["cpi"] / df["cpi"].shift(120)) ** (1 / 10) - 1
        real_rate = df["rate"] - infl10 * 100
        return (cape_yield - real_rate).dropna()

    raise KeyError(f"Onbekende Shiller-reeks: {name}")


if __name__ == "__main__":
    for n in ("CAPE", "ECY", "REALPRICE", "REALTR"):
        try:
            s = shiller_series(n)
            print(f"  {n:<10} {len(s):>5} waarnemingen  "
                  f"{s.index[0]:%Y-%m} t/m {s.index[-1]:%Y-%m}  "
                  f"laatste: {s.iloc[-1]:,.1f}")
        except Exception as e:
            print(f"  {n:<10} MISLUKT: {e}")
