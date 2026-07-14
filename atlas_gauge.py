#!/usr/bin/env python3
"""
ATLAS als FRAGILITEITSMETER — niet als alarmklok.

Waarom dit script apart staat:
atlas_jst.py toetst "stond de score hoog in de 2 jaar VOOR de crisis?". Dat is de
vraag van een vroegwaarschuwingssysteem. Maar het is NIET de vraag die ATLAS moet
beantwoorden - en het straft precies het gedrag dat we willen.

Japan bouwde zijn zeepbel op van ~1975 tot 1989. Een meter die dat correct
oppikt, staat vanaf 1980 hoog. De AUC-test rekent de jaren 1980-1986 dan af als
VALSE ALARMEN, want er volgde geen crisis binnen 2 jaar. Het model wordt gestraft
voor het zien van de opbouw. Vandaar Japans AUC van 0,49: mogelijk niet omdat het
model faalde, maar omdat de test de verkeerde vraag stelde.

Dit script stelt de goede vragen:

  1. TRAJECT     - loopt de score gestaag op tijdens een opbouw? (Japan 1975-1995)
  2. HOOGTE      - hoe hoog stond hij op het moment van de klap, vergeleken met
                   de eigen historie van dat land?
  3. DREMPEL     - wat gebeurt er NA een score van 70+? Hoe vaak volgt er een
                   crisis binnen 3, 5, 10 jaar? Dat is de "slaap ik hier slecht
                   van"-vraag, en het is de enige die telt voor een belegger.
  4. HORIZON     - bij welke waarschuwingstermijn werkt het model het best?
                   Als de AUC stijgt naarmate het venster langer wordt, dan meet
                   ATLAS een TRAGE cyclus - precies zoals bedoeld.

Gebruik:
    python3 atlas_gauge.py
    python3 atlas_gauge.py --land Japan
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from atlas_jst import (load_jst, build_signals, to_scores, auc, WEIGHTS)


def build_panel() -> pd.DataFrame:
    raw = load_jst()
    rows = []
    for country, g in raw.groupby("country"):
        sc = to_scores(build_signals(g))
        num = sum(sc[n].fillna(0) * w for n, w in WEIGHTS.items())
        den = sum(sc[n].notna() * w for n, w in WEIGHTS.items())
        atlas = (num / den.replace(0, np.nan)).where(den >= 0.5)
        atlas = atlas.rolling(2, min_periods=1).mean()
        crisis = g.set_index("year")["crisisJST"].fillna(0).reindex(atlas.index)
        rows.append(pd.DataFrame({"land": country, "jaar": atlas.index,
                                  "atlas": atlas.values, "crisis": crisis.values}))
    return pd.concat(rows).dropna(subset=["atlas"]).reset_index(drop=True)


# --- 1 & 2. Traject en hoogte op het moment van de klap ---------------------
def trajectory(P: pd.DataFrame, land: str, span: int = 20):
    g = P[P.land == land].set_index("jaar")
    crises = g.index[g.crisis == 1].tolist()
    if not crises:
        print(f"  Geen crises gedateerd voor {land}.")
        return

    print(f"\n  TRAJECT — {land}")
    for cr in crises:
        w = g.loc[(g.index >= cr - span) & (g.index <= cr + 3)]
        if w.empty:
            continue
        print(f"\n    Crisis {cr}. Score per jaar in de {span} jaar ervoor:")
        for yr, r in w.iterrows():
            v = r["atlas"]
            bar = "#" * int(v / 3)
            mark = "  <<< CRISIS" if r["crisis"] == 1 else ""
            print(f"      {int(yr)}  {v:5.1f} {bar:<34}{mark}")


def height_at_crisis(P: pd.DataFrame):
    """Hoe hoog stond de meter op het moment van de klap, t.o.v. de eigen historie?"""
    print("\n  HOOGTE OP HET MOMENT VAN DE KLAP")
    print("  (percentiel = hoe hoog stond de score in het jaar VOOR de crisis,")
    print("   vergeleken met alle jaren van datzelfde land)\n")
    print(f"    {'land':<16}{'crisis':>7}{'score':>7}{'percentiel':>12}")

    rec = []
    for land, g in P.groupby("land"):
        g = g.set_index("jaar")
        for cr in g.index[g.crisis == 1]:
            if cr - 1 not in g.index:
                continue
            v = g.loc[cr - 1, "atlas"]
            pct = 100 * (g["atlas"] < v).mean()
            rec.append({"land": land, "crisis": int(cr), "score": v, "pct": pct})

    df = pd.DataFrame(rec).sort_values("pct", ascending=False)
    for _, r in df.iterrows():
        flag = "" if r["pct"] >= 70 else "   << meter stond LAAG"
        print(f"    {r['land']:<16}{r['crisis']:>7}{r['score']:>7.1f}"
              f"{r['pct']:>11.0f}%{flag}")

    print(f"\n    Mediaan percentiel bij een crisis: {df['pct'].median():.0f}%")
    print(f"    Crises met de meter boven het 70e percentiel: "
          f"{(df['pct'] >= 70).mean():.0%}")
    print(f"    Crises met de meter boven het 50e percentiel: "
          f"{(df['pct'] >= 50).mean():.0%}")
    return df


# --- 3. De drempelvraag: wat volgt er NA een hoge score? --------------------
def threshold_table(P: pd.DataFrame):
    """Als de meter boven X staat: hoe vaak volgt er dan een crisis binnen N jaar?
    Dit is de vraag van een belegger, niet van een statisticus."""
    print("\n  DE DREMPELVRAAG — als de meter boven X staat, wat volgt er dan?")
    print("  (kans op een crisis binnen N jaar, gemeten over alle 18 landen)\n")

    fut = {}
    for h in (3, 5, 10):
        col = []
        for land, g in P.groupby("land"):
            g = g.sort_values("jaar")
            c = g["crisis"].values
            n = len(c)
            f = [1 if c[i + 1:min(i + 1 + h, n)].sum() > 0 else 0 for i in range(n)]
            col.append(pd.Series(f, index=g.index))
        fut[h] = pd.concat(col)

    base = {h: fut[h].mean() for h in fut}
    print(f"    {'meterstand':<16}" + "".join(f"{f'<{h}jr':>10}" for h in (3, 5, 10))
          + f"{'  jaren':>9}")
    print(f"    {'ALLE JAREN':<16}" + "".join(f"{base[h]:>9.0%}" for h in (3, 5, 10))
          + f"{len(P):>9}")
    print("    " + "-" * 52)

    for lo, hi in [(0, 40), (40, 60), (60, 70), (70, 80), (80, 101)]:
        m = (P["atlas"] >= lo) & (P["atlas"] < hi)
        if m.sum() < 20:
            continue
        row = "".join(f"{fut[h][m.values].mean():>9.0%}" for h in (3, 5, 10))
        label = f"{lo}-{hi if hi < 101 else 100}"
        print(f"    {label:<16}{row}{m.sum():>9}")

    print("\n    Lees de rij 70-80 en 80-100: DAT is het antwoord op 'moet ik hier")
    print("    slecht van slapen?'. Vergelijk met de bovenste rij (alle jaren) —")
    print("    dat is het risico zonder enige informatie. Het verschil is wat")
    print("    ATLAS je oplevert.")


# --- 4. Bij welke horizon werkt het model? ---------------------------------
def horizon_scan(P: pd.DataFrame):
    print("\n  HORIZON — bij welke waarschuwingstermijn werkt het model het best?\n")
    print(f"    {'venster':<12}{'AUC':>8}")
    for h in (1, 2, 3, 5, 7, 10):
        ys = []
        for land, g in P.groupby("land"):
            g = g.sort_values("jaar")
            c = g["crisis"].values
            n = len(c)
            ys.append(pd.Series(
                [1 if c[i + 1:min(i + 1 + h, n)].sum() > 0 else 0 for i in range(n)],
                index=g.index))
        y = pd.concat(ys)
        a = auc(P["atlas"], y)
        print(f"    {h:>2} jaar     {a:.3f}")
    print("\n    Stijgt de AUC met een langer venster, dan meet ATLAS een TRAGE")
    print("    opbouw en geen scherp alarm. Dat is geen zwakte — dat is precies")
    print("    wat een fragiliteitsmeter hoort te doen.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--land", default="Japan")
    a = ap.parse_args()

    P = build_panel()
    print("\n" + "=" * 66)
    print("  ATLAS ALS FRAGILITEITSMETER")
    print("=" * 66)
    print(f"\n  {P.land.nunique()} landen | {len(P)} landjaren | "
          f"{int(P.crisis.sum())} crises")

    horizon_scan(P)
    height_at_crisis(P)
    threshold_table(P)
    trajectory(P, a.land)
    print()
