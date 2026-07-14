#!/usr/bin/env python3
"""
ATLAS — validatie op het Jorda-Schularick-Taylor panel.

DE ENIGE ECHTE TEST.

Alles wat we tot nu toe deden was in-sample. We hebben vier Amerikaanse crises
bekeken, richtingen omgedraaid, indicatoren geschrapt en toegevoegd, drempels
bijgesteld — en toen op diezelfde vier crises gemeten. Dat kan niet anders dan
mooie cijfers opleveren. De AUC van 0,90 zegt daarom niets over de toekomst.

Dit script doet het omgekeerde. Het neemt de JST Macrohistory Database:
18 landen, 1870-heden, met ~50 gedateerde bankencrises. Zweden 1991, Japan 1990,
Finland 1991, Noorwegen 1987, Spanje 2008, Duitsland 1931... Crises waar we NOOIT
naar gekeken hebben en waar dus niets aan te overfitten valt.

DE REGEL: geen enkele knop wordt hier nog gedraaid. De richtingen liggen vast
zoals we ze op de VS kozen. Wat er uitkomt, komt eruit.

  AUC > 0,75  -> het mechanisme generaliseert. Je hebt iets echts.
  AUC 0,6-0,75-> zwak maar reeel. De VS-score van 0,90 was opgeblazen.
  AUC < 0,6   -> we hebben vier Amerikaanse crises uit het hoofd geleerd.

Data: https://www.macrohistory.net/database/  (gratis, registratie niet nodig)
Het script probeert te downloaden. Lukt dat niet, download dan handmatig
JSTdatasetR6.xlsx en zet het in deze map.

Gebruik:
    python3 atlas_jst.py
    python3 atlas_jst.py --per-land     # ook de uitsplitsing per land
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.filters.hp_filter import hpfilter

URLS = [
    "https://data.macrohistory.net/JST/JSTdatasetR6.xlsx",
    "https://data.macrohistory.net/JST/JSTdatasetR5.xlsx",
]
LOCAL = ["JSTdatasetR6.xlsx", "JSTdatasetR5.xlsx", "JSTdataset.xlsx", "jst.xlsx"]

# Ravn-Uhlig: lambda schaalt met de frequentie^4. De BIS gebruikt 400.000 voor
# kwartaaldata; voor jaardata is het equivalent 400.000 / 4^4 = 1.562,5.
HP_LAMBDA_ANNUAL = 1562.5

WARN_YEARS = 2       # de 2 jaar VOOR een crisis = "had gewaarschuwd moeten worden"
AFTER_YEARS = 3      # de 3 jaar NA een crisis worden gemaskeerd in de soepele test
MIN_YEARS = 20       # minimale historie per land voor een z-score/percentiel

# ---------------------------------------------------------------------------
# De indicatoren. Elke richting is OVERGENOMEN uit het VS-model. Niets nieuws.
# ---------------------------------------------------------------------------
INDICATORS = {
    # naam:            (bouwfunctie,          richting, ATLAS-tegenhanger)
    "Credit-to-GDP gap":        ("credit_gap",   +1, "Credit-to-GDP gap"),
    "Kredietratio Δ3jr":        ("credit_d3",    +1, "Kredietratio, 3-jaars verandering"),
    "Reele geldgroei":          ("money_growth", +1, "Reele M2-groei"),
    "Huizenprijs / inkomen":    ("hp_income",    +1, "Huizenprijs / inkomen"),
    "Huizenprijs, reeel":       ("hp_real",      +1, "Huizenprijs / huur (proxy)"),
    "Yield curve (lang-kort)":  ("yield_curve",  -1, "Yield curve 10j-3m"),
}

# Pijlergewichten, overgenomen uit ATLAS en genormaliseerd over wat JST heeft.
WEIGHTS = {
    "Credit-to-GDP gap":       0.15,
    "Kredietratio Δ3jr":       0.15,
    "Reele geldgroei":         0.10,
    "Huizenprijs / inkomen":   0.15,
    "Huizenprijs, reeel":      0.15,
    "Yield curve (lang-kort)": 0.30,
}


# ---------------------------------------------------------------------------
def load_jst() -> pd.DataFrame:
    import requests
    tried = []
    for url in URLS:
        try:
            r = requests.get(url, timeout=90, headers={"User-Agent": "ATLAS/1.0"})
            r.raise_for_status()
            df = pd.read_excel(io.BytesIO(r.content), sheet_name=0)
            print(f"  JST opgehaald van {url}")
            return df
        except Exception as e:
            tried.append(f"{url}: {str(e)[:60]}")
    for p in LOCAL:
        if Path(p).exists():
            print(f"  JST gelezen uit lokaal bestand: {p}")
            return pd.read_excel(p, sheet_name=0)
        tried.append(f"{p}: niet gevonden")
    sys.exit(
        "JST-data niet gevonden.\n  Geprobeerd:\n    " + "\n    ".join(tried)
        + "\n\n  Download handmatig van https://www.macrohistory.net/database/"
          "\n  en zet JSTdatasetR6.xlsx in deze map."
    )


def one_sided_hp_gap(s: pd.Series, min_obs: int = 15) -> pd.Series:
    """Point-in-time: op jaar t alleen data t/m t."""
    out = pd.Series(np.nan, index=s.index)
    v = s.dropna()
    for i in range(min_obs, len(v) + 1):
        w = v.iloc[:i]
        try:
            _, trend = hpfilter(w, lamb=HP_LAMBDA_ANNUAL)
            out.loc[w.index[-1]] = w.iloc[-1] - trend.iloc[-1]
        except Exception:
            pass
    return out


def build_signals(g: pd.DataFrame) -> pd.DataFrame:
    """Bouwt de indicatoren voor EEN land. Alles point-in-time."""
    g = g.sort_values("year").set_index("year")
    out = pd.DataFrame(index=g.index)

    credit_gdp = 100 * g["tloans"] / g["gdp"]
    out["credit_gap"] = one_sided_hp_gap(credit_gdp)
    out["credit_d3"] = credit_gdp.diff(3)

    real_money = g["money"] / g["cpi"]
    out["money_growth"] = real_money.pct_change(3) * 100

    real_hp = g["hpnom"] / g["cpi"]
    out["hp_real"] = one_sided_hp_gap(real_hp / real_hp.iloc[:5].mean() * 100)

    income_pc = (g["gdp"] / g["cpi"]) / g["pop"]
    out["hp_income"] = one_sided_hp_gap(real_hp / income_pc * 100)

    out["yield_curve"] = g["ltrate"] - g["stir"]
    return out


def to_scores(sig: pd.DataFrame) -> pd.DataFrame:
    """Zelfde recept als ATLAS: cyclische z-score + seculair percentiel, 0-100.
    Expanding, dus point-in-time."""
    sc = pd.DataFrame(index=sig.index)
    for name, (col, direction, _) in INDICATORS.items():
        s = sig[col]
        mu = s.expanding(min_periods=MIN_YEARS).mean()
        sd = s.expanding(min_periods=MIN_YEARS).std()
        z = ((s - mu) / sd) * direction
        cyc = (50 + 50 * z / 2.0).clip(0, 100)
        sec = 100 * (s * direction).expanding(min_periods=MIN_YEARS).rank(pct=True)
        sc[name] = pd.concat([cyc, sec], axis=1).mean(axis=1, skipna=True)
    return sc


def auc(scores: pd.Series, y: pd.Series) -> float:
    pos, neg = scores[y == 1].dropna(), scores[y == 0].dropna()
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    allv = pd.concat([pos, neg])
    r = allv.rank()
    return float((r.iloc[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)))


# ---------------------------------------------------------------------------
def main(per_land: bool):
    raw = load_jst()
    need = {"year", "country", "crisisJST", "tloans", "gdp", "cpi",
            "hpnom", "money", "stir", "ltrate", "pop"}
    missing = need - set(raw.columns)
    if missing:
        sys.exit(f"Kolommen ontbreken in het JST-bestand: {sorted(missing)}\n"
                 f"  Gevonden: {sorted(raw.columns)[:25]}")

    rows = []
    for country, g in raw.groupby("country"):
        sig = build_signals(g)
        sc = to_scores(sig)

        num = sum(sc[n].fillna(0) * w for n, w in WEIGHTS.items())
        den = sum(sc[n].notna() * w for n, w in WEIGHTS.items())
        atlas = (num / den.replace(0, np.nan)).where(den >= 0.5)
        # gladstrijken over 2 jaar (jaardata; in de VS was dit 12 maanden)
        atlas = atlas.rolling(2, min_periods=1).mean()

        crisis = g.set_index("year")["crisisJST"].fillna(0)
        pre = pd.Series(0, index=atlas.index)
        after = pd.Series(False, index=atlas.index)
        for yr in crisis[crisis == 1].index:
            pre[(pre.index >= yr - WARN_YEARS) & (pre.index < yr)] = 1
            after[(after.index >= yr) & (after.index <= yr + AFTER_YEARS)] = True

        d = pd.DataFrame({"land": country, "jaar": atlas.index, "atlas": atlas.values,
                          "pre": pre.values, "na": after.values,
                          "crisis": crisis.reindex(atlas.index).values})
        for n in WEIGHTS:
            d[n] = sc[n].values
        rows.append(d)

    P = pd.concat(rows).dropna(subset=["atlas"])
    n_cris = int(P["crisis"].sum())
    n_land = P["land"].nunique()

    soepel = P[~P["na"].astype(bool)]
    a_soepel = auc(soepel["atlas"], soepel["pre"])
    a_streng = auc(P["atlas"], P["pre"])

    print("\n" + "=" * 70)
    print("  ATLAS op het JST-panel — DE ECHTE TEST")
    print("=" * 70)
    print(f"\n  {n_land} landen | {len(P)} landjaren | {n_cris} bankencrises")
    print(f"  Basisrate: {P['pre'].mean():.1%} van de jaren is 'pre-crisis'")
    print("\n  Geen enkele parameter is op deze data afgesteld. De richtingen")
    print("  komen ongewijzigd uit het VS-model.\n")

    print(f"  AUC SOEPEL : {a_soepel:.3f}")
    print(f"  AUC STRENG : {a_streng:.3f}   <<< HET OORDEEL")
    v = ("Het mechanisme generaliseert. Dit is echt." if a_streng > 0.75 else
         "Zwak maar reeel. De VS-score van 0,90 was opgeblazen." if a_streng > 0.60 else
         "Het model heeft vier Amerikaanse crises uit het hoofd geleerd.")
    print(f"\n  OORDEEL: {v}")

    print("\n  AUC per indicator (streng, gepoold over alle landen):")
    for n in WEIGHTS:
        a = auc(P[n], P["pre"])
        tag = ("sterk" if a >= 0.70 else "matig" if a >= 0.60 else
               "zwak " if a >= 0.50 else "OMGEKEERD")
        print(f"    {a:.3f}  {tag:<9} {n}")

    if per_land:
        print("\n  Per land (alleen landen met >=2 crises):")
        for land, g in P.groupby("land"):
            nc = int(g["crisis"].sum())
            if nc < 2:
                continue
            a = auc(g["atlas"], g["pre"])
            if not np.isnan(a):
                print(f"    {a:.3f}   {land:<18} ({nc} crises, {len(g)} jaar)")

    P.to_csv("atlas_jst.csv", index=False)
    print("\n  Volledige reeks -> atlas_jst.csv")
    print("\n  LET OP: JST is JAARdata met minder indicatoren dan het VS-model")
    print("  (geen CAPE, margin debt, schaduwkrediet). Dit toetst het MECHANISME,")
    print("  niet het volledige model. Een lagere AUC dan de VS is dus deels te")
    print("  verwachten - maar niet zoveel lager dat er niets overblijft.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-land", action="store_true")
    main(ap.parse_args().per_land)
