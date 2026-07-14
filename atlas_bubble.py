#!/usr/bin/env python3
"""
ATLAS — DE ZEEPBELTOETS.

De vorige uitkomst was hard: AUC 0,47 op aandelenzeepbellen. Geen signaal.
Maar die test was op twee punten oneerlijk, en dat wisten we vooraf:

  1. De JST-versie van ATLAS heeft GEEN ENKELE aandelenindicator. Kredietgap,
     kredietgroei, geldgroei, huizen, yieldcurve - dat is alles. We vroegen een
     kredietmodel om beurscrashes te voorspellen zonder het een beursgetal te
     geven. Dat het faalt is geen ontdekking maar rekenkunde.

  2. 89 "zeepbellen" in 1997 landjaren is er een per 22 jaar. Daar zitten
     wereldoorlogen, olieschokken en hyperinflaties bij. Een reele daling van
     35% in 1914 of 1940 is geen geknapte zeepbel maar een invasie. Geen enkel
     fragiliteitsmodel ziet dat aankomen, en het hoort het niet te proberen.

Dit script repareert beide en toetst opnieuw. Twee toevoegingen:

  Aandelen / BBP        - de reele aandelenindex gedeeld door het reele BBP.
                          Het JST-equivalent van de Buffett-indicator, en de
                          beste benadering van CAPE die dit panel toelaat.
  Aandelen t.o.v. trend - de afwijking van de reele aandelenindex van zijn
                          eigen langjarige trend.

En: standaard alleen data VANAF 1950, zodat oorlogscrashes eruit vallen.

DE VOORSPELLING, hier vastgelegd VOOR de uitvoering, zodat er achteraf niet
weggedraaid kan worden: de AUC voor aandelenzeepbellen stijgt van 0,47 naar
0,60 a 0,70. Gebeurt dat niet, dan is de conclusie definitief - ATLAS meet
bankfragiliteit en niets anders, en activazeepbellen vergen een eigen model.

Het script draait ELKE toets twee keer: zonder en met de aandelenindicatoren.
Zo zie je wat de toevoeging werkelijk doet, in plaats van alleen het eindcijfer.

Gebruik:
    python3 atlas_bubble.py
    python3 atlas_bubble.py --vanaf 1870     # ook de oorlogsjaren, ter vergelijking
"""

from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd

from atlas_jst import (load_jst, build_signals, to_scores, auc, WEIGHTS,
                       one_sided_hp_gap, MIN_YEARS)
from atlas_events import find_busts, EQ_DROP, EQ_WIN, HP_DROP, HP_WIN

warnings.filterwarnings("ignore", category=FutureWarning)

# De twee nieuwe indicatoren. Richting +1: duur = fragiel. Zelfde logica als
# CAPE en Buffett in het VS-model, dus geen nieuwe vrijheidsgraad.
EQ_WEIGHTS = {"Aandelen / BBP": 0.20, "Aandelen t.o.v. trend": 0.15}


def build_equity_signals(g: pd.DataFrame) -> pd.DataFrame:
    """Aandelenwaardering uit JST. LET OP: eq_tr is TOTAALrendement, dus inclusief
    dividend. De index drijft daardoor sneller omhoog dan de koers alleen. De
    HP-trend vangt die drift weg - we kijken naar de AFWIJKING, niet het niveau."""
    g = g.sort_values("year").set_index("year")
    out = pd.DataFrame(index=g.index)

    if "eq_tr" not in g.columns:
        out["eq_gdp"] = np.nan
        out["eq_trend"] = np.nan
        return out

    nominal = (1 + g["eq_tr"].fillna(0)).cumprod()
    eq_real = nominal / g["cpi"]
    gdp_real = g["gdp"] / g["cpi"]

    ratio = eq_real / gdp_real
    out["eq_gdp"] = one_sided_hp_gap(100 * ratio / ratio.iloc[:5].mean())
    out["eq_trend"] = one_sided_hp_gap(100 * eq_real / eq_real.iloc[:5].mean())
    return out


def score_equity(sig: pd.DataFrame) -> pd.DataFrame:
    sc = pd.DataFrame(index=sig.index)
    for name, col in [("Aandelen / BBP", "eq_gdp"),
                      ("Aandelen t.o.v. trend", "eq_trend")]:
        s = sig[col]
        mu = s.expanding(min_periods=MIN_YEARS).mean()
        sd = s.expanding(min_periods=MIN_YEARS).std()
        cyc = (50 + 50 * ((s - mu) / sd) / 2.0).clip(0, 100)
        sec = 100 * s.expanding(min_periods=MIN_YEARS).rank(pct=True)
        sc[name] = pd.concat([cyc, sec], axis=1).mean(axis=1, skipna=True)
    return sc


def composite(sc: pd.DataFrame, weights: dict) -> pd.Series:
    num = sum(sc[n].fillna(0) * w for n, w in weights.items() if n in sc)
    den = sum(sc[n].notna() * w for n, w in weights.items() if n in sc)
    c = (num / den.replace(0, np.nan)).where(den >= 0.5)
    return c.rolling(2, min_periods=1).mean()


def build_panel(vanaf: int) -> pd.DataFrame:
    raw = load_jst()
    rows = []
    for country, g in raw.groupby("country"):
        g = g.sort_values("year")
        sc = to_scores(build_signals(g))
        sce = score_equity(build_equity_signals(g))
        both = pd.concat([sc, sce], axis=1)

        zonder = composite(sc, WEIGHTS)
        met = composite(both, {**WEIGHTS, **EQ_WEIGHTS})

        gi = g.set_index("year")
        cpi = gi["cpi"]
        if "eq_tr" in gi:
            eqr = (1 + gi["eq_tr"].fillna(0)).cumprod() / cpi
            eq_bust = find_busts(eqr, EQ_DROP, EQ_WIN)
        else:
            eq_bust = pd.Series(0, index=gi.index)
        hp_bust = find_busts(gi["hpnom"] / cpi, HP_DROP, HP_WIN)

        d = pd.DataFrame({
            "land": country, "jaar": zonder.index,
            "zonder": zonder.values, "met": met.values,
            "bank": gi["crisisJST"].reindex(zonder.index).fillna(0).values,
            "aandelen": eq_bust.reindex(zonder.index).fillna(0).values,
            "huizen": hp_bust.reindex(zonder.index).fillna(0).values,
        })
        d["welke_dan_ook"] = ((d.bank + d.aandelen + d.huizen) > 0).astype(int)
        rows.append(d)

    P = pd.concat(rows).reset_index(drop=True)
    return P[P.jaar >= vanaf].dropna(subset=["zonder", "met"]).reset_index(drop=True)


def future_flag(P: pd.DataFrame, col: str, h: int) -> pd.Series:
    out = []
    for _, g in P.groupby("land"):
        g = g.sort_values("jaar")
        c = g[col].values
        n = len(c)
        out.append(pd.Series(
            [1 if c[i + 1:min(i + 1 + h, n)].sum() > 0 else 0 for i in range(n)],
            index=g.index))
    return pd.concat(out).reindex(P.index)


TYPES = [("bank", "Bankencrisis"), ("aandelen", "Aandelenzeepbel"),
         ("huizen", "Huizenzeepbel"), ("welke_dan_ook", "Welke dan ook")]


def main(vanaf: int):
    P = build_panel(vanaf)
    print("\n" + "=" * 72)
    print(f"  DE ZEEPBELTOETS   (vanaf {vanaf})")
    print("=" * 72)
    print(f"\n  {P.land.nunique()} landen | {len(P)} landjaren")
    print(f"    {'gebeurtenis':<18}{'aantal':>8}")
    for c, label in TYPES:
        print(f"    {label:<18}{int(P[c].sum()):>8}")

    print("\n  AUC — venster 2 jaar. Twee kolommen: het model ZONDER")
    print("  aandelenindicatoren, en MET. Het verschil is wat ze opleveren.\n")
    print(f"    {'gebeurtenis':<18}{'zonder':>9}{'met':>9}{'verschil':>11}")
    res = {}
    for c, label in TYPES:
        y = future_flag(P, c, 2)
        a0, a1 = auc(P["zonder"], y), auc(P["met"], y)
        res[c] = (a0, a1)
        d = a1 - a0
        print(f"    {label:<18}{a0:>9.3f}{a1:>9.3f}{d:>+11.3f}")

    # Het oordeel over de voorspelling, zonder ontsnappingsroute.
    a1 = res["aandelen"][1]
    print("\n  " + "-" * 68)
    print("  DE VOORSPELLING WAS: aandelen-AUC tussen 0,60 en 0,70.")
    if a1 >= 0.60:
        print(f"  UITKOMST: {a1:.3f} — de voorspelling houdt stand. Met een")
        print("  waarderingssignaal ziet ATLAS ook aandelenzeepbellen.")
    else:
        print(f"  UITKOMST: {a1:.3f} — de voorspelling FAALT.")
        print("  De conclusie is dan definitief: ATLAS meet bankfragiliteit.")
        print("  Aandelenzeepbellen knappen op een eigen ritme dat dit model")
        print("  niet vangt. Zet dat zo in het dashboard, of bouw er een")
        print("  apart instrument voor - maar doe niet alsof.")
    print("  " + "-" * 68)

    for c, label in TYPES:
        print(f"\n  DREMPELTABEL — {label}  (model MET aandelen)\n")
        f = {h: future_flag(P, c, h) for h in (3, 5, 10)}
        print(f"    {'meterstand':<14}" + "".join(f"{f'<{h}jr':>9}" for h in (3, 5, 10))
              + f"{'jaren':>8}")
        print(f"    {'ALLE JAREN':<14}"
              + "".join(f"{f[h].mean():>9.0%}" for h in (3, 5, 10)) + f"{len(P):>8}")
        print("    " + "-" * 46)
        for lo, hi in [(0, 40), (40, 60), (60, 70), (70, 80), (80, 101)]:
            m = (P["met"] >= lo) & (P["met"] < hi)
            if m.sum() < 20:
                continue
            row = "".join(f"{f[h][m].mean():>9.0%}" for h in (3, 5, 10))
            print(f"    {f'{lo}-{min(hi,100)}':<14}{row}{m.sum():>8}")

    P.to_csv("atlas_bubble.csv", index=False)
    print("\n  -> atlas_bubble.csv\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--vanaf", type=int, default=1950)
    main(ap.parse_args().vanaf)
