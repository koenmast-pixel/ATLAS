#!/usr/bin/env python3
"""
ATLAS-ZEEPBEL — de tweede wijzer.

WAAROM DIT BESTAAT
Het JST-panel zei: AUC 0,54 op aandelenzeepbellen. Geen signaal. Maar dat panel
mist juist de indicatoren die zeepbellen verraden - het heeft geen margin debt,
geen huishoudallocatie, geen CAPE. Ik moest het doen met surrogaten uit een
rendementsreeks, en die faalden.

Kijk daarentegen naar de crisis-autopsie van het VS-model:

    indicator                     1987   2000   2007   2022
    Margin debt / BBP               99     97     35     96
    Aandelenallocatie huishoudens   37     98     87     98
    Shiller CAPE                    52     99     90     95

Margin debt staat op 99 en 97 voor de twee grote BEURSCRASHES, en zakt naar 35
voor de KREDIETcrisis van 2007. Dat is geen ruis - dat is een indicator die
precies onderscheidt waar hij voor bedoeld is. Hij hoort niet in de kredietmeter
thuis, hij hoort in een eigen meter.

Vandaar twee wijzers op het dashboard:

    ATLAS-KREDIET  - breekt het krediet? (banken, schuld, huizen, liquiditeit)
                     Gevalideerd op 61 crises in 18 landen. AUC 0,68.
    ATLAS-ZEEPBEL  - breekt de prijs? (CAPE, ECY, Buffett, margin debt, allocatie)
                     Dit script.

EERLIJKHEID VOORAF - lees dit voordat je het cijfer gelooft
De richtingen van deze vijf indicatoren zijn gekozen na inzage in de Amerikaanse
historie. Dit is dus GEEN out-of-sample test zoals het JST-panel dat was. De AUC
die hieruit komt is een bovengrens, geen belofte. Het aantal gebeurtenissen is
klein (~8 crashes sinds 1881). Behandel dit als een goed onderbouwd meetinstrument,
niet als bewijs.

Wat het WEL is: de crashes worden gedateerd uit de data zelf (Shiller, reele
koers, daling >30%), niet handmatig gekozen. Dat scheelt een vrijheidsgraad.

Gebruik:
    export FRED_API_KEY=...
    python3 atlas_equity.py --fetch
    python3 atlas_equity.py
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from atlas import INDICATORS, score_series
from atlas_backtest import load_data      # hergebruikt het bestaande cachemechanisme

DROP = 0.30        # reele daling van >30% ...
WIN = 36           # ... binnen 36 maanden vanaf de top
PRE = 24           # het waarschuwingsvenster: de 24 mnd voor de top
SMOOTH = 12

# De vijf indicatoren die een ZEEPBEL verraden, met hun gewicht.
# Alle vijf zitten al in atlas.py; hier krijgen ze een eigen weging.
BUBBLE = {
    "Shiller CAPE": 0.25,                    # duurste maatstaf met de langste historie
    "Excess CAPE Yield": 0.20,               # duur T.O.V. obligaties - vangt 2000 en 2022
    "Beurswaarde / BBP (Buffett)": 0.20,     # beurs t.o.v. de echte economie
    "Margin debt / BBP": 0.20,               # geleend geld in de markt = de hefboom
    "Aandelenallocatie huishoudens": 0.15,   # wie is er al binnen? niemand meer om te kopen
}


def real_price() -> pd.Series:
    try:
        from atlas_shiller import shiller_series
        return shiller_series("REALPRICE").resample("ME").last()
    except Exception as e:
        sys.exit(f"Shiller-koersreeks niet beschikbaar: {e}\n"
                 f"  Zorg dat atlas_shiller.py in deze map staat (met .py!).")


def forward_returns(tr: pd.Series, years: int) -> pd.Series:
    """Het reele TOTAALrendement over de komende N jaar, op jaarbasis.

    Dit is de vraag die je WEL kunt beantwoorden. Crashes zijn zeldzaam (3 in
    onze reeks) - daar valt niets op te toetsen. Maar het verband tussen
    waardering en het rendement daarna is een van de best gerepliceerde
    bevindingen in de financiele economie, en daarvoor heb je honderd jaar aan
    overlappende vensters.

    De vraag verschuift van "wanneer knapt het?" (onbeantwoordbaar) naar
    "wat levert deze markt me hierna nog op?" (beantwoordbaar, en voor een
    belegger nuttiger).
    """
    n = years * 12
    fwd = (tr.shift(-n) / tr) ** (1 / years) - 1
    return fwd * 100


def melt_up(p: pd.Series) -> pd.Series:
    """DE MELT-UP. Niet hoe duur de markt is, maar hoe HARD hij nog stijgt.

    Greenwood, Shleifer & You (2019) toonden aan: een hoge waardering alleen
    voorspelt slechte RENDEMENTEN, maar niet WANNEER het knapt. Een scherpe
    koersstijging alleen evenmin. De COMBINATIE wel. Duur en zijwaarts is een
    ander regime dan duur en verticaal.

    Drie componenten, elk als percentiel van de eigen historie:
      - 12-maands reeel rendement   (hoe hard ging het het afgelopen jaar?)
      - 24-maands reeel rendement   (is dit een aanhoudende run?)
      - VERSNELLING: het laatste jaar t.o.v. het tienjaars gemiddelde.
        Dit is de kern. Een markt die al tien jaar 8% doet is geen zeepbel.
        Een markt die 40% doet na jaren van 8% is een melt-up.
    """
    r12 = p.pct_change(12)
    r24 = p.pct_change(24)
    accel = r12 - p.pct_change(120) / 10      # laatste jaar min de 10-jaars trend

    parts = []
    for s_ in (r12, r24, accel):
        parts.append(100 * s_.expanding(min_periods=120).rank(pct=True))
    return pd.concat(parts, axis=1).mean(axis=1, skipna=True)


def find_crashes(p: pd.Series) -> list[pd.Timestamp]:
    """Dateert de crashes uit de data zelf: elke TOP waarna de reele koers
    binnen WIN maanden meer dan DROP daalt. Springt over de crash heen, zodat
    de daling zelf niet als reeks toppen wordt geteld."""
    v = p.dropna()
    out, i = [], 0
    while i < len(v):
        val = v.iloc[i]
        fut = v.iloc[i + 1:i + 1 + WIN]
        if len(fut) and (fut.min() / val - 1) <= -DROP and fut.max() <= val:
            out.append(v.index[i])
            i += WIN
        else:
            i += 1
    return out


def auc(s: pd.Series, y: pd.Series) -> float:
    pos, neg = s[y == 1].dropna(), s[y == 0].dropna()
    if not len(pos) or not len(neg):
        return np.nan
    r = pd.concat([pos, neg]).rank()
    return float((r.iloc[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)))


def main(fetch: bool):
    inds = [i for i in INDICATORS if i.name in BUBBLE]
    data = load_data(fetch=fetch, demo=False)
    missing = [i.name for i in inds if i.name not in data]
    if missing:
        sys.exit(f"Niet in de cache: {missing}\n"
                 f"  Draai eerst: python3 atlas_equity.py --fetch")

    cols = {}
    for ind in inds:
        if ind.name in data:
            ss, _ = score_series(data[ind.name], ind)
            if ss is not None:
                cols[ind.name] = ss
    df = pd.DataFrame(cols)

    num = sum(df[n].fillna(0) * w for n, w in BUBBLE.items() if n in df)
    den = sum(df[n].notna() * w for n, w in BUBBLE.items() if n in df)
    score = (num / den.replace(0, np.nan)).where(den >= 0.5)
    score = score.rolling(SMOOTH, min_periods=6).mean().dropna()
    # GEEN tweede ijking. De losse indicatoren zijn al 0-100 geijkt; er nog een
    # percentielrang overheen leggen vernietigt het signaal (CAPE haalde los 0,76,
    # de dubbelgeijkte samenstelling 0,49). Dit was een echte fout, geen detail.

    p = real_price()
    melt = melt_up(p).reindex(score.index).ffill()

    # DE COMBINATIE. Bewust multiplicatief, niet optellend: een gemiddelde
    # laat een torenhoge waardering een lauwe melt-up compenseren, en dat is
    # precies het regime dat NIET gevaarlijk is (Japan 1992: nog steeds duur,
    # maar de melt-up was voorbij - en er kwam geen tweede crash).
    # Multiplicatief betekent: ALLEBEI hoog, of het telt niet.
    combi = np.sqrt(score.clip(lower=0) * melt.clip(lower=0))

    crashes = find_crashes(p)
    crashes = [c for c in crashes if c >= score.index[0]]

    y = pd.Series(0, index=score.index)
    for c in crashes:
        y[(y.index >= c - pd.DateOffset(months=PRE)) & (y.index < c)] = 1

    print("\n" + "=" * 68)
    print("  ATLAS-ZEEPBEL — breekt de PRIJS?")
    print("=" * 68)
    print(f"\n  Periode: {score.index[0]:%Y-%m} t/m {score.index[-1]:%Y-%m}"
          f"   ({len(score)} maanden)")
    print(f"  Crashes gedateerd uit de data (reeel >{DROP:.0%} binnen "
          f"{WIN} mnd): {len(crashes)}")
    print("    " + ", ".join(f"{c:%Y-%m}" for c in crashes))

    print("\n  DRIE METERS NAAST ELKAAR (AUC streng, elke maand telt):\n")
    print(f"    {'meter':<34}{'AUC':>8}")
    for label, s_ in [("WAARDERING (duur?)", score),
                      ("MELT-UP (versnelt het?)", melt),
                      ("COMBINATIE (duur EN versnelt)", combi)]:
        ai = auc(s_, y)
        v = ("sterk" if ai > 0.8 else "bruikbaar" if ai > 0.7 else
             "zwak" if ai > 0.6 else "geen signaal")
        print(f"    {label:<34}{ai:>8.3f}   {v}")

    a = auc(combi, y)
    a_val = auc(score, y)
    print("\n  DE TOETS VAN JOUW HYPOTHESE:")
    if a > a_val + 0.02:
        print(f"    De combinatie ({a:.3f}) verslaat waardering alleen "
              f"({a_val:.3f}).")
        print("    Duur EN versnellend is inderdaad gevaarlijker dan duur alleen.")
    else:
        print(f"    De combinatie ({a:.3f}) verslaat waardering alleen "
              f"({a_val:.3f}) NIET.")
        print("    De melt-up voegt in deze data niets toe. Hypothese verworpen.")

    print("\n  LET OP: in-sample. De richtingen zijn op deze data gekozen.")
    print("  Vergelijk met ATLAS-KREDIET: 0,68 out-of-sample op 61 crises.")
    score_for_table = combi

    print("\n  AUC per indicator:")
    for n in BUBBLE:
        if n in df:
            ai = auc(df[n], y.reindex(df[n].index).fillna(0))
            tag = ("sterk" if ai >= 0.70 else "matig" if ai >= 0.60 else
                   "zwak" if ai >= 0.50 else "OMGEKEERD")
            print(f"    {ai:.3f}  {tag:<9} {n}")

    print("\n  AUTOPSIE — indicatorstand 12 mnd voor elke crash:")
    hdr = "".join(f"{c:%Y}"[:4].rjust(7) for c in crashes)
    print(f"    {'indicator':<32}{hdr}")
    for n in BUBBLE:
        if n not in df:
            continue
        row = ""
        for c in crashes:
            t = c - pd.DateOffset(months=12) + pd.offsets.MonthEnd(0)
            val = df[n].reindex([t]).iloc[0]
            row += f"{val:>7.0f}" if pd.notna(val) else f"{'-':>7}"
        print(f"    {n:<32}{row}")

    print("\n  DREMPELTABEL — kans op een beurscrash binnen N jaar:\n")
    fut = {}
    for h in (2, 3, 5):
        f = pd.Series(0, index=score.index)
        for c in crashes:
            f[(f.index >= c - pd.DateOffset(months=12 * h)) & (f.index < c)] = 1
        fut[h] = f
    print(f"    {'meterstand':<14}" + "".join(f"{f'<{h}jr':>9}" for h in (2, 3, 5))
          + f"{'mnd':>8}")
    print(f"    {'ALLE MAANDEN':<14}"
          + "".join(f"{fut[h].mean():>9.0%}" for h in (2, 3, 5)) + f"{len(score):>8}")
    print("    " + "-" * 46)
    for lo, hi in [(0, 40), (40, 60), (60, 70), (70, 80), (80, 101)]:
        m = (score_for_table >= lo) & (score_for_table < hi)
        if m.sum() < 12:
            continue
        row = "".join(f"{fut[h][m].mean():>9.0%}" for h in (2, 3, 5))
        print(f"    {f'{lo}-{min(hi,100)}':<14}{row}{m.sum():>8}")

    t = score.index[-1]
    print(f"\n  STAND VAN VANDAAG ({t:%Y-%m})")
    print(f"    Waardering : {score.iloc[-1]:5.1f}")
    print(f"    Melt-up    : {melt.iloc[-1]:5.1f}")
    print(f"    COMBINATIE : {combi.iloc[-1]:5.1f}   <<<")
    print("\n    onderliggend:")
    for n in BUBBLE:
        if n in df and pd.notna(df[n].iloc[-1]):
            print(f"      {df[n].iloc[-1]:>5.0f}  {n}")

    # ---------------------------------------------------------------
    #  WAT LEVERT DEZE MARKT HIERNA OP?
    # ---------------------------------------------------------------
    from atlas_shiller import shiller_series
    tr = shiller_series("REALTR").resample("ME").last()

    for horizon in (10, 5):
        fwd = forward_returns(tr, horizon).reindex(score.index)
        print(f"\n  REEEL RENDEMENT OVER DE VOLGENDE {horizon} JAAR (incl. dividend,")
        print("  na inflatie, op jaarbasis) - GEGEVEN DE WAARDERING VAN NU:\n")
        print(f"    {'waardering':<14}{'mediaan':>9}{'slechtste':>11}"
              f"{'beste':>8}{'kans <0%':>10}{'mnd':>7}")
        print("    " + "-" * 59)
        for lo, hi in [(0, 40), (40, 60), (60, 80), (80, 101)]:
            m = (score >= lo) & (score < hi) & fwd.notna()
            if m.sum() < 24:
                continue
            f = fwd[m]
            print(f"    {f'{lo}-{min(hi,100)}':<14}{f.median():>8.1f}%"
                  f"{f.min():>10.1f}%{f.max():>7.1f}%"
                  f"{(f < 0).mean():>9.0%}{m.sum():>7}")

        cur = score.iloc[-1]
        lo = 80 if cur >= 80 else 60 if cur >= 60 else 40 if cur >= 40 else 0
        hi = 101 if lo == 80 else lo + 20 if lo >= 60 else 60 if lo == 40 else 40
        m = (score >= lo) & (score < hi) & fwd.notna()
        if m.sum() >= 24:
            f = fwd[m]
            print(f"\n    De meter staat nu op {cur:.0f}. Historisch leverde die stand")
            print(f"    een mediaan van {f.median():+.1f}% per jaar op over {horizon} jaar,")
            print(f"    met een slechtste uitkomst van {f.min():+.1f}% en "
                  f"{(f < 0).mean():.0%} kans op verlies.")

    print("\n  LET OP - overlappende vensters. 673 maanden lijkt veel, maar")
    print("  opeenvolgende 10-jaars periodes delen 90% van hun data. Het echte")
    print("  aantal onafhankelijke waarnemingen is eerder 6 dan 600. De richting")
    print("  van het verband is robuust en breed gerepliceerd; de precieze")
    print("  percentages zijn dat niet.")

    pd.DataFrame({"waardering": score, "melt_up": melt,
                  "combinatie": combi}).to_csv("atlas_equity.csv")
    print("\n  -> atlas_equity.csv\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    main(ap.parse_args().fetch)


# ----------------------------------------------------------------------
#  Voor het dashboard
# ----------------------------------------------------------------------
def export_payload(data: dict) -> dict:
    from atlas_shiller import shiller_series
    """Levert de zeepbelmeter aan atlas_export.py.

    LET OP bij het tonen: deze meter is NIET gevalideerd. Er zijn maar vier
    bruikbare beurscrashes sinds 1960; elke AUC daarop is ruis. Wat hier WEL
    betekenis heeft is de rendementstabel - het verband tussen waardering en
    het rendement daarna is een van de best gerepliceerde bevindingen in de
    financiele economie.
    """
    inds = [i for i in INDICATORS if i.name in BUBBLE]
    cols = {}
    for ind in inds:
        if ind.name in data:
            ss, _ = score_series(data[ind.name], ind)
            if ss is not None:
                cols[ind.name] = ss
    df = pd.DataFrame(cols)

    num = sum(df[n].fillna(0) * w for n, w in BUBBLE.items() if n in df)
    den = sum(df[n].notna() * w for n, w in BUBBLE.items() if n in df)
    score = (num / den.replace(0, np.nan)).where(den >= 0.5)
    score = score.rolling(SMOOTH, min_periods=6).mean().dropna()

    p = real_price()
    melt = melt_up(p).reindex(score.index).ffill()
    combi = np.sqrt(score.clip(lower=0) * melt.clip(lower=0))

    tr = shiller_series("REALTR").resample("ME").last()

    tabellen = {}
    for h in (10, 5):
        fwd = forward_returns(tr, h).reindex(score.index)
        rijen = []
        for lo, hi in [(0, 40), (40, 60), (60, 80), (80, 101)]:
            m = (score >= lo) & (score < hi) & fwd.notna()
            if m.sum() < 24:
                continue
            f = fwd[m]
            rijen.append({"band": f"{lo}-{min(hi, 100)}",
                          "mediaan": round(float(f.median()), 1),
                          "slechtste": round(float(f.min()), 1),
                          "beste": round(float(f.max()), 1),
                          "kans_verlies": round(float((f < 0).mean()), 2),
                          "maanden": int(m.sum())})
        tabellen[f"j{h}"] = rijen

    t = score.index[-1]
    return {
        "waardering": round(float(score.iloc[-1]), 1),
        "meltup": round(float(melt.iloc[-1]), 1),
        "combinatie": round(float(combi.iloc[-1]), 1),
        "datum": str(t.date()),
        "indicatoren": [
            {"naam": n, "stand": round(float(df[n].dropna().iloc[-1]), 0),
             "weging": w}
            for n, w in BUBBLE.items() if n in df and df[n].notna().any()
        ],
        "rendement": tabellen,
        "crashes": [f"{c:%Y-%m}" for c in find_crashes(p)],
        "gevalideerd": False,
    }
