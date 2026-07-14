#!/usr/bin/env python3
"""
ATLAS - Mapping the Global Financial Cycle
Advanced Tracking of Long-term Asset Stability

v2 - wat er veranderde na de eerste echte FRED-run:
  1. FALLBACKS. Elke indicator heeft meerdere kandidaat-serie-ID's. FRED hernoemt
     en beeindigt series (WILL5000PRFC bestaat niet meer). Faalt de eerste, dan
     volgt de volgende. Een dode serie sloopt niet langer een hele pijler.
  2. ECHTE RATIO'S. De "Buffett-indicator" deelde in v1 nergens door het BBP.
     Nu wel. En "reeel" is nu echt reeel: gedefleerd met de CPI.
  3. EENHEDEN. De BIS credit-to-GDP gap is in PROCENTPUNTEN, niet procenten.
     v1 rekende een procentuele afwijking en toetste die aan een pp-drempel.
     Nu expliciet per indicator: gap_type = "pp" of "pct".
  4. TRANSPARANTIE. Elke run rapporteert welke series faalden en welke pijlers
     daardoor dun zijn. Een score met 60% dekking is geen score.

Gebruik:
    export FRED_API_KEY=...
    python atlas.py            # stand van vandaag
    python atlas.py --demo     # synthetische data, geen key nodig
    python atlas.py --json
"""

from __future__ import annotations  # Python 3.9-compatibel

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import requests
from statsmodels.tsa.filters.hp_filter import hpfilter

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
HP_LAMBDA = 400_000          # BIS-standaard: financiele cycli duren 15-20 jaar
ROLL_WINDOW_YEARS = 20
MIN_OBS_YEARS = 10
MIN_COVERAGE = 0.70          # daaronder is de totaalscore niet te vertrouwen
MIN_SIGNAL_MONTHS = 300      # ~25 jaar. Korter = hooguit een crisis gezien.
                             # Zo'n indicator mag meepraten in de diagnostiek,

# ---------------------------------------------------------------------
#  BEWUST UIT DE SCORE GEHOUDEN
#
#  Consumentenvertrouwen is geen aanjager van de cyclus maar een REFLECTIE
#  ervan. Huishoudens reageren op wat er al gebeurd is - ze veroorzaken het
#  niet. Dezelfde fout die we eerder bij M2-krimp en beleidsonzekerheid vonden:
#  gelijklopend, niet voorlopend.
#
#  Concreet aanleiding: de indicator stond op 0 terwijl margin debt (84) en de
#  aandelenallocatie (94) in dezelfde pijler op recordhoogte stonden. Het
#  gemiddelde daarvan is misleidend - een somber publiek MET recordhefboom is
#  iets anders dan een somber publiek ZONDER hefboom, en dat verschil kan een
#  simpel gemiddelde niet uitdrukken.
#
#  Hij blijft wel zichtbaar op het dashboard, net als de Fed-balans en de
#  reverse repo. Je ziet hem, hij telt niet mee.
# ---------------------------------------------------------------------
UIT_DE_SCORE = {"Consumentenvertrouwen"}

                             # maar niet meetellen in de score: zijn AUC is dan
                             # anekdote met decimalen, geen statistiek.
                             # (Dit haalt o.a. de Fed-balans eruit: strenge AUC
                             #  0,943 op 153 maanden = precies EEN gebeurtenis.)


@dataclass
class Indicator:
    name: str
    series: list                 # kandidaat-ID's, in volgorde van voorkeur
    pillar: str
    transform: str               # hp_gap | roll_z | yoy_z | diff_z | exp_pct
    direction: int = 1           # +1 = hoger gevaarlijker, -1 = lager gevaarlijker
    freq: str = "QE"
    units: str = "lin"
    denom: list = field(default_factory=list)   # deel hierdoor (bijv. BBP)
    minus: list = field(default_factory=list)        # trek deze reeks af...
    minus_denom: list = field(default_factory=list)  # ...gedeeld door deze
    minus_scale: float = 1.0                         # ...maal deze factor
    deflate: bool = False        # deel door CPI -> reeel
    gap_type: str = "pct"        # hp_gap: "pct" (relatief) of "pp" (absoluut)
    scale_ref: float = 2.0       # waarde die op score ~100 uitkomt
    lookback: int = 0            # diff_z: verandering over n perioden
    source: str = "fred"         # "fred" of "shiller"
    note: str = ""


CPI = ["CPIAUCSL"]
GDP = ["GDP"]

INDICATORS = [
    # --- Krediet & Liquiditeit (30%) ---
    Indicator("Credit-to-GDP gap", ["CRDQUSAPABIS", "QUSPAM770A"], "credit",
              "hp_gap", +1, "QE", gap_type="pp", scale_ref=20.0,
              note="BIS-gap in procentpunten. Let op: scale_ref stond op 10 (de "
                   "BIS-alarmdrempel), maar de Amerikaanse gap overschrijdt die "
                   "structureel. Gevolg: de indicator zat jarenlang gepind op 100 en "
                   "onderscheidde niets meer - hij stond op 100 bij ALLE vijf crises "
                   "EN ertussenin. Nu 20pp, zodat er weer variatie in zit."),
    Indicator("Kredietratio, 3-jaars verandering", ["CRDQUSAPABIS", "QUSPAM770A"],
              "credit", "diff_z", +1, "QE", lookback=12,
              note="Momentum van de kredietratio: de snelheid, niet het niveau."),
    Indicator("Reverse repo (RRP)", ["RRPONTSYD"], "credit", "roll_z", -1, "ME",
              note="Leegloop = de liquiditeitsbuffer raakt op."),
    Indicator("Niet-bancair krediet / BBP", ["CRDQUSAPABIS"], "credit",
              "hp_gap", +1, "QE", gap_type="pp", scale_ref=15.0,
              minus=["TOTBKCR"], minus_denom=GDP, minus_scale=100.0,
              note="Totaal privaat krediet (BIS, %BBP) MINUS bankkrediet (%BBP). "
                   "Wat overblijft is de hefboom BUITEN de banken: schaduwbanken, "
                   "securitisatie, private credit. In 2007 zat de crisis daar, niet "
                   "op de bankbalansen - en vandaag opnieuw. Benadering: de twee "
                   "bronnen tellen niet identiek, dus lees het NIVEAU niet, maar de "
                   "AFWIJKING VAN DE TREND."),
    Indicator("Reele M2-groei", ["M2REAL"], "credit", "yoy_z", +1, "ME",
              note="OMGEDRAAID in v3. Eerst: krimp = gevaar (AUC 0,18 - omgekeerd). "
                   "Nu: EXPANSIE = gevaar. Geldkrimp is de klap zelf, niet de "
                   "waarschuwing; overvloedige liquiditeit gaat aan elke zeepbel "
                   "vooraf. Zelfde logica als de kredietgap."),
    Indicator("Fed-balans, 12-mnd", ["WALCL"], "credit", "yoy_z", +1, "ME",
              note="OMGEDRAAID in v3 (AUC 0,21 - omgekeerd). QE voedt de opbouw, "
                   "QT is de nasleep."),

    # --- Waardering (20%) ---
    Indicator("Beurswaarde / BBP (Buffett)", ["NCBEILQ027S", "WILL5000INDFC"],
              "valuation", "hp_gap", +1, "QE", denom=GDP, gap_type="pct",
              scale_ref=40.0,
              note="Aandelen op bedrijfsbalansen (Fed Z.1) gedeeld door BBP. "
                   "Historie vanaf 1945. Trendgecorrigeerd: het niveau drift "
                   "seculair omhoog door globalisering en winstaandeel."),
    Indicator("Huizenprijs / huur", ["USSTHPI", "CSUSHPINSA"], "valuation",
              "hp_gap", +1, "QE", denom=["CUSR0000SEHA"], gap_type="pct",
              scale_ref=20.0,
              note="Huizenprijsindex gedeeld door de huurindex. DE klassieke "
                   "zeepbelmaatstaf voor vastgoed: kopen is duur t.o.v. huren "
                   "wanneer mensen kopen om de prijsstijging, niet om het dak. "
                   "FHFA-index vanaf 1975 (langer dan Case-Shiller, dat pas in "
                   "1987 begint - te kort voor een 20-jaars venster)."),
    Indicator("Huizenprijs / inkomen", ["USSTHPI", "CSUSHPINSA"], "valuation",
              "hp_gap", +1, "QE", denom=["A229RX0"], gap_type="pct", scale_ref=20.0,
              note="Huizenprijs gedeeld door het reeel besteedbaar inkomen per hoofd. "
                   "Meet de betaalbaarheid: als huizen sneller stijgen dan inkomens, "
                   "moet de rest met krediet worden overbrugd."),
    Indicator("High-yield spreads (OAS)", ["BAMLH0A0HYM2"], "valuation", "roll_z",
              -1, "ME",
              note="Te krappe spreads = complacency. Let op: korte historie."),
    Indicator("Shiller CAPE", ["CAPE"], "valuation", "exp_pct", +1, "ME",
              source="shiller",
              note="Cyclisch gecorrigeerde K/W, historie vanaf 1871. Middelt de "
                   "winst over 10 jaar en ontloopt zo het gebrek van forward P/E: "
                   "die staat op de cyclustop juist op zijn optimistischst."),
    Indicator("Excess CAPE Yield", ["ECY"], "valuation", "exp_pct", -1, "ME",
              source="shiller",
              note="(1/CAPE) min de reele 10-jaarsrente. LAAG = duur = gevaarlijk. "
                   "Corrigeert voor het renteregime, nodig om 2000 en 2026 te "
                   "kunnen vergelijken."),

    # --- Monetair & Rente (20%) ---
    Indicator("Yield curve 10j-3m", ["T10Y3M"], "monetary", "roll_z", -1, "ME",
              note="Inversie ging aan elke naoorlogse recessie vooraf."),


    # --- Gedrag & Marktstructuur (15%) ---
    Indicator("Consumentenvertrouwen", ["UMCSENT"], "behavior", "exp_pct", +1, "ME",
              note="Euforie-proxy."),
    Indicator("Margin debt / BBP", ["BOGZ1FL663067003Q"], "behavior", "hp_gap", +1, "QE",
              denom=GDP, gap_type="pct", scale_ref=30.0,
              note="Geleend geld op de beurs (Fed Z.1, vanaf 1945). Hefboom van "
                   "beleggers: piekt bij elke zeepbel. Gedeeld door BBP en "
                   "trendgecorrigeerd, want het niveau drift seculair omhoog."),
    Indicator("Aandelenallocatie huishoudens", ["BOGZ1FL153064486Q"], "behavior",
              "exp_pct", +1, "QE",
              note="Aandelen als % van de financiele bezittingen (Fed Z.1, vanaf 1945). "
                   "Volgens Philosophical Economics (2013) de sterkste bekende "
                   "voorspeller van het 10-jaars aandelenrendement - sterker dan CAPE. "
                   "Als iedereen al binnen is, is er niemand meer om te kopen."),

    # --- Geopolitiek & Maatschappij (15%) ---
    Indicator("Beleidsonzekerheid (EPU)", ["USEPUINDXD"], "geo", "roll_z", -1, "ME",
              note="OMGEDRAAID in v3 (AUC 0,34 - omgekeerd). LAGE onzekerheid = "
                   "complacency = gevaar. EPU piekt TIJDENS crises, niet ervoor. "
                   "Zwakste van de drie omkeringen: hou deze in de gaten."),
]

PILLARS = {
    "credit":    ("Krediet & Liquiditeit", 0.30),
    "valuation": ("Waardering",            0.20),
    "monetary":  ("Monetair & Rente",      0.20),
    "behavior":  ("Gedrag & Structuur",    0.20),
    "geo":       ("Geopolitiek & Sociaal", 0.10),
}

REGIMES = [(40, "EXPANSIE"), (60, "LATE CYCLE"), (80, "FRAGIEL"), (101, "KRITIEK")]


# ---------------------------------------------------------------------------
# Data ophalen
# ---------------------------------------------------------------------------
def fetch_one(series_id: str, api_key: str, units: str = "lin") -> pd.Series:
    r = requests.get(FRED_URL, timeout=30, params={
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "units": units, "observation_start": "1900-01-01"})
    r.raise_for_status()
    obs = r.json()["observations"]
    idx = [pd.Timestamp(o["date"]) for o in obs if o["value"] not in (".", "")]
    val = [float(o["value"]) for o in obs if o["value"] not in (".", "")]
    if not idx:
        raise ValueError("lege serie")
    return pd.Series(val, index=pd.DatetimeIndex(idx), name=series_id)


def fetch_first(candidates: list, api_key: str, units: str = "lin"):
    """Probeert de kandidaten op volgorde. Geeft (serie, gebruikt_id, fouten)."""
    errors = []
    for sid in candidates:
        try:
            return fetch_one(sid, api_key, units), sid, errors
        except Exception as e:
            errors.append(f"{sid}: {str(e).split(' for url')[0]}")
    return None, None, errors


def demo_series(seed: int, n_years: int = 50, freq: str = "ME") -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(
        start=pd.Timestamp.today().normalize() - pd.DateOffset(years=n_years),
        end=pd.Timestamp.today(), freq=freq)
    t = np.arange(len(idx))
    cycle = 10 * np.sin(2 * np.pi * t / (len(idx) / 3))
    return pd.Series(100 + np.cumsum(rng.normal(.05, 1, len(idx))) + cycle, index=idx)


def _align_divide(base: pd.Series, other: pd.Series) -> pd.Series:
    """Deelt base door other, met forward-fill (BBP is kwartaal, beurs is dagelijks)."""
    o = other.reindex(base.index.union(other.index)).ffill().reindex(base.index)
    return base / o


def build_indicator_input(ind: Indicator, api_key, demo: bool, seed: int):
    """Haalt de ruwe serie op en past ratio/deflatie toe. Geeft (serie, meta)."""
    if demo:
        return demo_series(seed, freq=ind.freq), {"used": "DEMO", "errors": []}

    meta = {"used": None, "errors": []}

    if ind.source == "shiller":
        try:
            from atlas_shiller import shiller_series
            s = shiller_series(ind.series[0])
            meta["used"] = f"Shiller:{ind.series[0]}"
            return s.dropna(), meta
        except Exception as e:
            meta["errors"] = [f"Shiller {ind.series[0]}: {str(e).splitlines()[0]}"]
            return None, meta

    s, used, errs = fetch_first(ind.series, api_key, ind.units)
    meta["errors"] = errs
    if s is None:
        return None, meta
    meta["used"] = used

    if ind.denom:
        d, dused, derrs = fetch_first(ind.denom, api_key)
        if d is None:
            meta["errors"] += derrs
            return None, meta
        meta["used"] += f" / {dused}"
        s = _align_divide(s, d)

    if ind.minus:
        m, mused, merrs = fetch_first(ind.minus, api_key)
        if m is None:
            meta["errors"] += merrs
            return None, meta
        if ind.minus_denom:
            md, mdused, mderrs = fetch_first(ind.minus_denom, api_key)
            if md is None:
                meta["errors"] += mderrs
                return None, meta
            m = _align_divide(m, md)
            mused += f"/{mdused}"
        m = m.reindex(s.index.union(m.index)).ffill().reindex(s.index)
        s = s - m * ind.minus_scale
        meta["used"] += f" - {mused}"

    if ind.deflate:
        c, cused, cerrs = fetch_first(CPI, api_key)
        if c is None:
            meta["errors"] += cerrs
            return None, meta
        meta["used"] += f" / {cused}"
        s = _align_divide(s, c)

    return s.replace([np.inf, -np.inf], np.nan).dropna(), meta


# ---------------------------------------------------------------------------
# Transformaties — allemaal point-in-time: op datum t alleen data t/m t
# ---------------------------------------------------------------------------
def one_sided_hp(s: pd.Series, min_obs: int, gap_type: str) -> pd.Series:
    out = pd.Series(np.nan, index=s.index)
    v = s.dropna()
    for i in range(min_obs, len(v) + 1):
        w = v.iloc[:i]
        _, trend = hpfilter(w, lamb=HP_LAMBDA)
        gap = w.iloc[-1] - trend.iloc[-1]
        out.loc[w.index[-1]] = gap if gap_type == "pp" else 100 * gap / trend.iloc[-1]
    return out


def rolling_z(s: pd.Series, w: int) -> pd.Series:
    mu = s.rolling(w, min_periods=w // 2).mean()
    sd = s.rolling(w, min_periods=w // 2).std()
    return (s - mu) / sd


def expanding_pct(s: pd.Series, min_obs: int) -> pd.Series:
    return s.expanding(min_periods=min_obs).rank(pct=True)


def signal_of(s: pd.Series, ind: Indicator):
    fpy = 12 if ind.freq == "ME" else 4
    s = s.resample(ind.freq).last().dropna()
    if len(s) < MIN_OBS_YEARS * fpy:
        return None, f"te weinig historie ({len(s) // fpy} jaar, minimaal {MIN_OBS_YEARS})"

    roll_w, min_obs = ROLL_WINDOW_YEARS * fpy, MIN_OBS_YEARS * fpy

    if ind.transform == "hp_gap":
        sig = one_sided_hp(s, min_obs, ind.gap_type)
    elif ind.transform == "roll_z":
        sig = rolling_z(s, roll_w)
    elif ind.transform == "yoy_z":
        sig = rolling_z(s.pct_change(fpy) * 100, roll_w)
    elif ind.transform == "diff_z":
        sig = rolling_z(s.diff(ind.lookback), roll_w)
    elif ind.transform == "exp_pct":
        sig = expanding_pct(s, min_obs)
    else:
        return None, f"onbekende transformatie: {ind.transform}"

    sig = sig.dropna()
    return (sig, None) if len(sig) else (None, "geen signaal na transformatie")


def score_series(s: pd.Series, ind: Indicator):
    """Volledige maandelijkse scorereeks, 0-100 (hoger = fragieler)."""
    sig, err = signal_of(s, ind)
    if sig is None:
        return None, err

    fpy = 12 if ind.freq == "ME" else 4
    min_obs = MIN_OBS_YEARS * fpy

    if ind.transform == "exp_pct":
        cyc = 100 * (sig if ind.direction > 0 else 1 - sig)
    else:
        cyc = (50 + 50 * sig * ind.direction / ind.scale_ref).clip(0, 100)

    sec = 100 * expanding_pct(sig * ind.direction, min(min_obs, len(sig)))

    out = pd.concat([cyc, sec], axis=1).mean(axis=1, skipna=True)
    return out.resample("ME").last().ffill(limit=3), None


# ---------------------------------------------------------------------------
# Aggregatie
# ---------------------------------------------------------------------------
def run(api_key, demo: bool = False) -> dict:
    results = {}
    for i, ind in enumerate(INDICATORS):
        s, meta = build_indicator_input(ind, api_key, demo, seed=i)
        if s is None:
            results[ind.name] = {"pillar": ind.pillar, "used": None,
                                 "error": "; ".join(meta["errors"]) or "geen data"}
            continue
        ss, err = score_series(s, ind)
        if ss is None or ss.dropna().empty:
            results[ind.name] = {"pillar": ind.pillar, "used": meta["used"],
                                 "error": err or "lege reeks"}
            continue
        last = ss.dropna()
        results[ind.name] = {"pillar": ind.pillar, "used": meta["used"],
                             "score": round(float(last.iloc[-1]), 1),
                             "per": str(last.index[-1].date()), "note": ind.note}

    pillars, total, wsum = {}, 0.0, 0.0
    for key, (label, weight) in PILLARS.items():
        got = [r["score"] for r in results.values()
               if r["pillar"] == key and "score" in r]
        n_total = sum(1 for i in INDICATORS if i.pillar == key)
        if got:
            ps = float(np.mean(got))
            pillars[label] = {"score": round(ps, 1), "weight": weight,
                              "n": len(got), "n_total": n_total}
            total += ps * weight
            wsum += weight
        else:
            pillars[label] = {"score": None, "weight": weight,
                              "n": 0, "n_total": n_total}

    atlas = round(total / wsum, 1) if wsum else None
    ok = sum(1 for r in results.values() if "score" in r)
    return {
        "atlas": atlas,
        "regime": next(n for c, n in REGIMES if atlas < c) if atlas is not None else None,
        "coverage": round(wsum, 2),
        "reliable": bool(wsum >= MIN_COVERAGE and ok >= len(INDICATORS) * 0.7),
        "indicators_ok": ok, "indicators_total": len(INDICATORS),
        "pillars": pillars, "results": results,
    }


def report(out: dict) -> None:
    print("\n" + "=" * 68)
    print("  ATLAS - Mapping the Global Financial Cycle")
    print("=" * 68)
    if not out["reliable"]:
        print("\n  !! ONBETROUWBAAR - te veel indicatoren ontbreken.")
        print("     Lees de score hieronder als systeemtest, niet als meting.")
    print(f"\n  SCORE   : {out['atlas']}  ->  {out['regime']}")
    print(f"  Dekking : {out['coverage']:.0%} van het pijlergewicht"
          f"   ({out['indicators_ok']}/{out['indicators_total']} indicatoren)\n")

    for label, p in out["pillars"].items():
        v = p["score"] or 0
        bar = "#" * int(v / 5) + "." * (20 - int(v / 5))
        thin = "  << DUN" if 0 < p["n"] < p["n_total"] else ""
        print(f"  {label:<24} {str(p['score']):>6}  [{bar}]  "
              f"{p['n']}/{p['n_total']}{thin}")

    print("\n  Indicatoren:")
    for name, r in out["results"].items():
        if "score" in r:
            print(f"   OK    {name:<34} {r['score']:>5}   [{r['used']}]")
    fails = [(n, r) for n, r in out["results"].items() if "score" not in r]
    if fails:
        print("\n  Gefaald:")
        for name, r in fails:
            print(f"   FOUT  {name:<34} {r['error']}")

    print("\n  ATLAS meet fragiliteit, geen timing.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    key = os.environ.get("FRED_API_KEY")
    if not a.demo and not key:
        sys.exit("Zet FRED_API_KEY, of draai met --demo")

    o = run(key, a.demo)
    print(json.dumps(o, indent=2, ensure_ascii=False)) if a.json else report(o)
