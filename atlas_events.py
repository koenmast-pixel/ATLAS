#!/usr/bin/env python3
"""
ATLAS — TWEE SOORTEN KLAPPEN.

Het inzicht dat dit script afdwingt:
een systeemcrash kan twee wortels hebben, en ze zijn niet hetzelfde.

  BANKENCRISIS   — het krediet breekt. Banken vallen om, de kredietverlening
                   stopt, de reele economie volgt. Zweden 1991, VS 2008.
                   Deze staan gedateerd in JST (crisisJST).

  ACTIVAZEEPBEL  — de prijs breekt. Aandelen of huizen storten in zonder dat
                   het bankwezen per se omvalt. Japan 1989, dotcom 2000.
                   Deze staan NIET in JST — dus leiden we ze zelf af.

Waarom dat verschil telt: JST noemt Japans bankencrisis 1997, niet 1989. De
zeepbel knapte in december 1989; de banken hielden het nog zeven jaar vol als
zombies. Meet je alleen bankencrises, dan ziet het eruit alsof het model Japan
miste. In werkelijkheid piekte de meter in 1987 - twee jaar voor de zeepbel.

Definities (bewust simpel en vooraf vastgelegd, niet achteraf bijgesteld):
  Aandelenzeepbel knapt = een reele daling van >35% vanaf de top, binnen 3 jaar.
                          Het EVENT is het jaar van de TOP, niet van de bodem.
  Huizenzeepbel knapt   = een reele daling van >15% vanaf de top, binnen 5 jaar.
                          Huizen dalen trager en minder diep dan aandelen.

Gebruik:
    python3 atlas_events.py
    python3 atlas_events.py --land Japan
"""

from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd

from atlas_jst import load_jst, build_signals, to_scores, auc, WEIGHTS

warnings.filterwarnings("ignore", category=FutureWarning)

EQ_DROP, EQ_WIN = 0.35, 3      # aandelen: >35% reeel, binnen 3 jaar
HP_DROP, HP_WIN = 0.15, 5      # huizen:   >15% reeel, binnen 5 jaar


# ---------------------------------------------------------------------------
def find_busts(real_index: pd.Series, drop: float, win: int) -> pd.Series:
    """Markeert het jaar van de TOP waarna een reele daling van >drop volgt."""
    ev = pd.Series(0, index=real_index.index)
    v = real_index.dropna()
    i = 0
    while i < len(v):
        val = v.iloc[i]
        fut = v.iloc[i + 1:i + 1 + win]
        # Twee eisen: er volgt een daling van >drop, EN dit is de echte top
        # (niets in het venster ligt hoger).
        if len(fut) and (fut.min() / val - 1) <= -drop and fut.max() <= val:
            ev.loc[v.index[i]] = 1
            i += win      # over de crash heen springen. Zonder deze sprong
            #               wordt elk jaar VAN de daling opnieuw als "top"
            #               geteld - want vanaf daar daalt het immers ook nog.
        else:
            i += 1
    return ev


def build_panel() -> pd.DataFrame:
    raw = load_jst()
    has_eq = "eq_tr" in raw.columns

    rows = []
    for country, g in raw.groupby("country"):
        g = g.sort_values("year")
        sc = to_scores(build_signals(g))
        num = sum(sc[n].fillna(0) * w for n, w in WEIGHTS.items())
        den = sum(sc[n].notna() * w for n, w in WEIGHTS.items())
        atlas = (num / den.replace(0, np.nan)).where(den >= 0.5)
        atlas = atlas.rolling(2, min_periods=1).mean()

        gi = g.set_index("year")
        cpi = gi["cpi"]

        # --- reele aandelenindex uit het totaalrendement ---
        if has_eq:
            tr = gi["eq_tr"].fillna(0)
            nominal = (1 + tr).cumprod()
            eq_real = nominal / cpi
            eq_bust = find_busts(eq_real, EQ_DROP, EQ_WIN)
        else:
            eq_bust = pd.Series(0, index=gi.index)

        # --- reele huizenprijs ---
        hp_real = gi["hpnom"] / cpi
        hp_bust = find_busts(hp_real, HP_DROP, HP_WIN)

        bank = gi["crisisJST"].fillna(0)

        d = pd.DataFrame({
            "land": country, "jaar": atlas.index, "atlas": atlas.values,
            "bank": bank.reindex(atlas.index).fillna(0).values,
            "aandelen": eq_bust.reindex(atlas.index).fillna(0).values,
            "huizen": hp_bust.reindex(atlas.index).fillna(0).values,
        })
        d["welke_dan_ook"] = ((d.bank + d.aandelen + d.huizen) > 0).astype(int)
        rows.append(d)

    return pd.concat(rows).dropna(subset=["atlas"]).reset_index(drop=True)


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


TYPES = [("bank", "Bankencrisis"), ("aandelen", "Aandelenzeepbel knapt"),
         ("huizen", "Huizenzeepbel knapt"), ("welke_dan_ook", "WELKE DAN OOK")]


def main(land: str):
    P = build_panel()
    print("\n" + "=" * 72)
    print("  ATLAS — TWEE SOORTEN KLAPPEN")
    print("=" * 72)
    print(f"\n  {P.land.nunique()} landen | {len(P)} landjaren\n")
    print(f"    {'gebeurtenis':<24}{'aantal':>8}")
    for c, label in TYPES:
        print(f"    {label:<24}{int(P[c].sum()):>8}")

    # --- AUC per type, op 2 jaar vooruit ---
    print("\n  ONDERSCHEIDEND VERMOGEN (AUC), waarschuwingsvenster 2 jaar:\n")
    print(f"    {'gebeurtenis':<24}{'AUC':>7}   oordeel")
    for c, label in TYPES:
        y = future_flag(P, c, 2)
        a = auc(P["atlas"], y)
        v = ("sterk" if a >= 0.70 else "bruikbaar" if a >= 0.65 else
             "zwak" if a >= 0.55 else "geen signaal")
        print(f"    {label:<24}{a:>7.3f}   {v}")

    # --- de drempeltabel, per type ---
    for c, label in TYPES:
        print(f"\n  DREMPELTABEL — {label}")
        print("  (kans dat dit gebeurt binnen N jaar, gegeven de meterstand)\n")
        f = {h: future_flag(P, c, h) for h in (3, 5, 10)}
        print(f"    {'meterstand':<14}" + "".join(f"{f'<{h}jr':>9}" for h in (3, 5, 10))
              + f"{'jaren':>8}")
        print(f"    {'ALLE JAREN':<14}"
              + "".join(f"{f[h].mean():>9.0%}" for h in (3, 5, 10)) + f"{len(P):>8}")
        print("    " + "-" * 46)
        for lo, hi in [(0, 40), (40, 60), (60, 70), (70, 80), (80, 101)]:
            m = (P["atlas"] >= lo) & (P["atlas"] < hi)
            if m.sum() < 20:
                continue
            row = "".join(f"{f[h][m].mean():>9.0%}" for h in (3, 5, 10))
            print(f"    {f'{lo}-{min(hi,100)}':<14}{row}{m.sum():>8}")

    # --- traject van een land, met beide gebeurtenistypen ---
    g = P[P.land == land].set_index("jaar")
    if not g.empty:
        print(f"\n  TRAJECT — {land}  (B=bankencrisis, A=aandelen, H=huizen)\n")
        for yr, r in g.iterrows():
            if yr < 1970:
                continue
            tags = "".join(t for t, c in
                           (("B", "bank"), ("A", "aandelen"), ("H", "huizen"))
                           if r[c] == 1)
            v = r["atlas"]
            mark = f"  <<< {tags}" if tags else ""
            print(f"    {int(yr)}  {v:5.1f} {'#' * int(v / 3):<34}{mark}")

    P.to_csv("atlas_events.csv", index=False)
    print("\n  -> atlas_events.csv\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--land", default="Japan")
    main(ap.parse_args().land)
