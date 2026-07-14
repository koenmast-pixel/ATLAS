#!/usr/bin/env python3
"""
ATLAS Backtest v1 - validatie tegen historische crisispieken

Berekent de VOLLEDIGE historische ATLAS-scorereeks (niet alleen de laatste
waarde) en toetst of het model de bekende pieken zag aankomen:

    2000-03 (dotcom)      2007-10 (krediet)     1987-08 (Black Monday)
    1973-01 (olie/Nifty)  2020-02 (COVID*)      2022-01 (rente/inflatie)

    * COVID = exogene schok, telt NIET mee als crisis die voorspelbaar was.
      Wordt apart getoond: als ATLAS hier hoog stond, mat hij fragiliteit
      (die was er: hoge waarderingen, lage VIX), niet de trigger.

Toetsen:
  1. HIT RATE  - stond ATLAS >60 (fragiel) in de 24 mnd voor elke piek?
  2. AUC       - onderscheidt de score pre-crisis van rustige periodes?
                 (0,5 = muntworp; >0,7 bruikbaar; >0,8 sterk)
  3. FALSE POS - hoe vaak >80 zonder crisis binnen 24 mnd?
  4. LEAD TIME - hoeveel maanden voor de piek werd de drempel geraakt?
  5. WEGINGEN  - welke pijlerweging maximaliseert de AUC? (grid search)

ALLE transformaties zijn point-in-time (eenzijdige HP, rollende z, expanding
percentile): op datum t wordt uitsluitend data t/m t gebruikt. Geen look-ahead.

Gebruik:
    export FRED_API_KEY=...
    python atlas_backtest.py --fetch      # data ophalen + cachen (1x, ~1 min)
    python atlas_backtest.py              # backtest op de cache (offline)
    python atlas_backtest.py --demo       # synthetische data, geen key nodig
    python atlas_backtest.py --optimize   # + wegingen optimaliseren

Output: atlas_history.csv (maandreeks van alle scores) + rapport in de terminal.
"""

from __future__ import annotations  # Python 3.9-compatibel

import argparse
import itertools
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from atlas import (INDICATORS, PILLARS, UIT_DE_SCORE, build_indicator_input, score_series,
                   MIN_SIGNAL_MONTHS)

CACHE = Path("atlas_cache.pkl")
HISTORY_CSV = "atlas_history.csv"

# Cyclus-pieken (maand van de top; crisis volgt in de 6-18 mnd erna)
PEAKS = {
    "1929-09": "Grote Crash",
    "1937-03": "Recessie van 1937",
    "1973-01": "Nifty Fifty / oliecrisis",
    "1987-08": "Black Monday",
    "2000-03": "Dotcom",
    "2007-10": "Kredietcrisis",
    "2022-01": "Rente/inflatie-reset",
}
EXOGENOUS = {"2020-02": "COVID (exogeen - niet meegeteld in AUC)"}

WARN_WINDOW = 24     # maanden voor de piek waarin ATLAS 'aan' moet staan
MIN_COVERAGE = 0.50  # onder deze pijlerdekking is de score betekenisloos
SMOOTH_MONTHS = 12   # trailing venster: cycli zijn traag, de meetlat dus ook
THRESH_FRAGILE = 60
THRESH_CRITICAL = 80


# ---------------------------------------------------------------------------
# 1. Data: ophalen en cachen
# ---------------------------------------------------------------------------
def load_data(fetch: bool, demo: bool) -> dict[str, pd.Series]:
    """Haalt per indicator de (eventueel gedeelde/gedefleerde) reeks op."""
    if demo or fetch:
        key = os.environ.get("FRED_API_KEY")
        if not demo and not key:
            sys.exit("Zet FRED_API_KEY om data op te halen.")
        data = {}
        for i, ind in enumerate(INDICATORS):
            s_, meta = build_indicator_input(ind, key, demo, seed=i)
            if s_ is None:
                print(f"  MISLUKT  : {ind.name:<34} {'; '.join(meta['errors'])}")
                continue
            data[ind.name] = s_
            print(f"  opgehaald: {ind.name:<34} {s_.index[0].date()} -> "
                  f"{s_.index[-1].date()}  [{meta['used']}]")
        if not demo:
            pd.to_pickle(data, CACHE)
            print(f"\n  Gecachet in {CACHE}. Draai nu zonder --fetch (offline).\n")
        return data

    if not CACHE.exists():
        sys.exit("Geen cache. Draai eerst: python atlas_backtest.py --fetch")
    return pd.read_pickle(CACHE)


# ---------------------------------------------------------------------------
# 2. Volledige scorereeks per indicator (point-in-time)
# ---------------------------------------------------------------------------
def build_history(data: dict, weights: dict | None = None) -> pd.DataFrame:
    """Bouwt maand-DataFrame met indicator-, pijler- en totaalscores."""
    weights = weights or {k: w for k, (_, w) in PILLARS.items()}
    cols, thin = {}, []
    for ind in INDICATORS:
        if ind.name in data:
            ss, err = score_series(data[ind.name], ind)
            if ss is not None:
                cols[ind.name] = ss
                if len(ss.dropna()) < MIN_SIGNAL_MONTHS:
                    thin.append(ind.name)   # te korte historie: niet in de score
                elif ind.name in UIT_DE_SCORE:
                    thin.append(ind.name)   # bewust uitgesloten (zie atlas.py)
    df = pd.DataFrame(cols)

    # LAATST GEPUBLICEERDE WAARDE MEEDRAGEN.
    #
    # Kwartaalreeksen (margin debt, aandelenallocatie, Buffett, kredietgap) komen
    # met vertraging binnen. Zonder deze regel verdwijnt zo'n indicator uit het
    # model zodra hij een maand achterloopt, en wordt de pijler herberekend over
    # wat er toevallig nog wel is.
    #
    # Wat dat aanrichtte: in mei 2026 stonden margin debt op 84 en de
    # aandelenallocatie op 94, maar allebei liepen ze tot maart. De pijler
    # Gedrag & Structuur viel daardoor terug op consumentenvertrouwen alleen -
    # stand 0 - en kwam uit op 0,2. Een vijfde van het model stond op nul door
    # data die simpelweg nog niet gepubliceerd was. Het kopcijfer werd daar
    # kunstmatig laag van.
    #
    # Dit is GEEN blik vooruit. In mei weet je wat margin debt in maart was; dat
    # cijfer is gepubliceerd. Een analist gooit het niet weg omdat het twee
    # maanden oud is - hij draagt het mee tot er een nieuw cijfer komt. De limiet
    # van 6 maanden voorkomt dat een reeks die echt gestopt is eeuwig doorleeft.
    STALE_MONTHS = 6
    df = df.ffill(limit=STALE_MONTHS)

    df.attrs["thin"] = thin

    for key, (label, _) in PILLARS.items():
        members = [i.name for i in INDICATORS
                   if i.pillar == key and i.name in df and i.name not in thin]
        df[label] = df[members].mean(axis=1, skipna=True) if members else np.nan

    # Gewogen totaal; herweeg naar beschikbare pijlers (dekkingscorrectie)
    labels = {key: PILLARS[key][0] for key in PILLARS}
    num = sum(df[labels[k]].fillna(0) * weights[k] for k in PILLARS)
    den = sum(df[labels[k]].notna() * weights[k] for k in PILLARS)
    df["dekking"] = (den / sum(weights.values())).round(2)
    raw = (num / den.replace(0, np.nan)).round(2)
    raw = raw.where(df["dekking"] >= MIN_COVERAGE)   # te dun = geen score
    # GLADSTRIJKEN (v4). De ruwe score sprong in twee maanden van "expansie" naar
    # "kritiek". Dat is onmogelijk: financiele cycli duren 15-20 jaar (Drehmann,
    # Borio & Tsatsaronis 2012). Wat daar bewoog was ruis - een hik in de repomarkt,
    # een VIX-spike - die rechtstreeks doorsloeg naar de eindscore.
    # Een trailing 12-maands gemiddelde. Trailing, dus point-in-time: op datum t
    # wordt uitsluitend data t/m t gebruikt. Geen blik vooruit.
    raw = raw.rolling(SMOOTH_MONTHS, min_periods=SMOOTH_MONTHS // 2).mean()
    df["ATLAS_ruw"] = raw

    # IJKING. De ruwe score stond 62% van de tijd boven de 60: de schaal zei niets.
    # Oorzaak: de seculaire component is een expanding percentile van een reeks die
    # structureel stijgt (krediet, CAPE, beurswaarde/BBP drijven omhoog), en die
    # zit dus bijna altijd hoog.
    # Oplossing: de EINDSCORE is zelf een expanding percentile van de ruwe score.
    # "ATLAS = 85" betekent nu letterlijk: fragieler dan 85% van alle maanden ooit
    # gemeten. Point-in-time: op datum t telt alleen wat t/m t bekend was.
    # Let op: dit is een monotone transformatie, dus de AUC verandert er NIET van.
    # Het maakt de drempels eerlijk, niet het model beter.
    df["ATLAS"] = (100 * raw.expanding(min_periods=240).rank(pct=True)).round(2)
    return df


# ---------------------------------------------------------------------------
# 3. Evaluatie
# ---------------------------------------------------------------------------
def label_prewindow(index: pd.DatetimeIndex, peaks=PEAKS, window=WARN_WINDOW) -> pd.Series:
    """1 = binnen `window` maanden VOOR een piek; 0 = rustige periode."""
    y = pd.Series(0, index=index)
    for p in peaks:
        peak = pd.Timestamp(p) + pd.offsets.MonthEnd(0)
        start = peak - pd.DateOffset(months=window)
        y[(index > start) & (index <= peak)] = 1
    return y


def exclude_aftermath(index: pd.DatetimeIndex, months=24) -> pd.Series:
    """Maskeer de 24 mnd NA elke piek: daar is de score mechanisch laag/hoog
    door de crisis zelf, dat is geen eerlijke test."""
    mask = pd.Series(True, index=index)
    for p in list(PEAKS) + list(EXOGENOUS):
        peak = pd.Timestamp(p) + pd.offsets.MonthEnd(0)
        end = peak + pd.DateOffset(months=months)
        mask[(index > peak) & (index <= end)] = False
    return mask


def auc(scores: pd.Series, y: pd.Series) -> float:
    """AUC via Mann-Whitney U (geen sklearn nodig)."""
    pos, neg = scores[y == 1].dropna(), scores[y == 0].dropna()
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    allv = pd.concat([pos, neg])
    ranks = allv.rank()
    r_pos = ranks.iloc[:len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def evaluate(df: pd.DataFrame) -> dict:
    s = df["ATLAS"].dropna()
    y = label_prewindow(s.index)
    fair = exclude_aftermath(s.index)
    s_f, y_f = s[fair], y[fair]

    res = {"auc_totaal": auc(s_f, y_f), "n_maanden": len(s), "hits": [], "pijler_auc": {}}

    for key, (label, _) in PILLARS.items():
        if label in df:
            ps = df[label].dropna()
            res["pijler_auc"][label] = auc(ps[fair.reindex(ps.index, fill_value=False)],
                                           label_prewindow(ps.index)[fair.reindex(ps.index, fill_value=False)])

    # AUC per losse indicator: welke draagt bij, welke vergiftigt?
    res["ind_auc"] = {}
    for ind in INDICATORS:
        if ind.name in df:
            col = df[ind.name].dropna()
            if len(col) < 120:
                continue
            m = fair.reindex(col.index, fill_value=False)
            a = auc(col[m], label_prewindow(col.index)[m])
            a_str = auc(col, label_prewindow(col.index))
            if not np.isnan(a):
                res["ind_auc"][ind.name] = (a, ind.pillar, len(col), a_str)

    # Hit rate + lead time per piek
    for p, name in {**PEAKS, **EXOGENOUS}.items():
        peak = pd.Timestamp(p) + pd.offsets.MonthEnd(0)
        win = s[(s.index > peak - pd.DateOffset(months=WARN_WINDOW)) & (s.index <= peak)]
        if win.empty:
            res["hits"].append({"piek": p, "naam": name, "status": "geen data"})
            continue
        peak_score = win.iloc[-1]
        first_fragile = win[win >= THRESH_FRAGILE]
        lead = (peak.to_period("M") - first_fragile.index[0].to_period("M")).n \
            if not first_fragile.empty else None
        res["hits"].append({
            "piek": p, "naam": name,
            "score_op_piek": round(float(peak_score), 1),
            "max_score_24m": round(float(win.max()), 1),
            "hit": bool(win.max() >= THRESH_FRAGILE),
            "kritiek": bool(win.max() >= THRESH_CRITICAL),
            "lead_mnd": lead,
        })

    # False positives: >80 terwijl geen piek binnen 24 mnd (en niet in nasleep)
    # Hoe vaak staat de score sowieso boven de drempel? Als dat de helft van de
    # tijd is, zegt een "hit" niets: dan is de drempel gewoon te laag gezet.
    res["pct_boven_60"] = round(float((s_f >= THRESH_FRAGILE).mean()), 3)
    res["pct_boven_80"] = round(float((s_f >= THRESH_CRITICAL).mean()), 3)
    res["dekking_start"] = None

    # DE STRENGE TEST. Hierboven maskeren we de 24 maanden na elke crisis. Dat maakt
    # de opgave makkelijker dan de werkelijkheid: we vergelijken "aanloop naar een
    # crash" met "rustige tijden ver van elke crash", en gooien het lastige
    # middengebied weg. Gladde, langzame indicatoren profiteren daar onevenredig van:
    # die stijgen naar een piek en dalen erna, en juist die daling maskeren we.
    # In het echt moet je ELKE maand classificeren. Dus doen we dat hier ook.
    y_all = label_prewindow(s.index)
    res["auc_streng"] = auc(s, y_all)
    res["ind_auc_streng"] = {}

    fp = s_f[(s_f >= THRESH_CRITICAL) & (y_f == 0)]
    res["false_pos_maanden"] = len(fp)
    res["false_pos_periodes"] = sorted({d.strftime("%Y") for d in fp.index})
    res["basisrate"] = round(float(y_f.mean()), 3)
    return res


def leave_one_out(df: pd.DataFrame) -> dict:
    """De overfit-toets. Als de AUC instort zodra je een crisis weglaat, dan
    'kende' het model die ene crisis en heeft het niets algemeens geleerd.
    Een robuust model verliest hooguit een paar punten; een overfit model klapt in."""
    s = df["ATLAS"].dropna()
    fair = exclude_aftermath(s.index)
    s_f = s[fair]

    out = {}
    for drop in PEAKS:
        rest = {k: v for k, v in PEAKS.items() if k != drop}
        y = label_prewindow(s.index, peaks=rest)[fair]
        if y.sum() == 0:
            continue
        out[drop] = auc(s_f, y)

    # En andersom: hoe goed doet het model het op ELKE crisis apart?
    solo = {}
    for keep in PEAKS:
        y = label_prewindow(s.index, peaks={keep: PEAKS[keep]})[fair]
        if y.sum() == 0:
            continue
        solo[keep] = auc(s_f, y)
    return {"zonder": out, "alleen": solo}


def out_of_sample(df: pd.DataFrame, split: str = "1999-12-31") -> dict:
    """Toetst het model op crises NA de splitsdatum, met een score die alleen
    op eerdere data is geijkt. Beperking, en die is groot: de RICHTINGEN van de
    indicatoren zijn gekozen na inzage in de volledige historie. Dit is dus geen
    zuivere out-of-sample test - alleen de ijking is schoon, de modelkeuze niet.
    Echt zuiver testen kan alleen op data die we nooit gezien hebben: andere
    landen (Jorda-Schularick-Taylor)."""
    s = df["ATLAS"].dropna()
    fair = exclude_aftermath(s.index)
    cut = pd.Timestamp(split)

    res = {}
    for label, mask in (("voor " + split[:4], s.index <= cut),
                        ("na " + split[:4], s.index > cut)):
        m = fair & pd.Series(mask, index=s.index)
        y = label_prewindow(s.index)[m]
        if y.sum() == 0 or (y == 0).sum() == 0:
            res[label] = None
            continue
        res[label] = auc(s[m], y)
    return res


def optimize_weights(df: pd.DataFrame, step=0.05) -> tuple[dict, float]:
    """Grid search over pijlerwegingen die de AUC maximaliseert.
    Hergebruikt de al berekende pijlerscores (geen HP-herberekening).
    LET OP: in-sample optimalisatie op 5 events -> overfit-risico.
    Gebruik het als sanity check, niet als waarheid."""
    keys = list(PILLARS)
    labels = {k: PILLARS[k][0] for k in keys}
    P = df[[labels[k] for k in keys]]

    grid = [w for w in itertools.product(np.arange(0.05, 0.55, step), repeat=len(keys))
            if abs(sum(w) - 1.0) < 1e-9]

    best, best_auc = None, -1.0
    for w in grid:
        num = sum(P[labels[k]].fillna(0) * wk for k, wk in zip(keys, w))
        den = sum(P[labels[k]].notna() * wk for k, wk in zip(keys, w))
        s = (num / den.replace(0, np.nan)).dropna()
        fair = exclude_aftermath(s.index)
        a = auc(s[fair], label_prewindow(s.index)[fair])
        if not np.isnan(a) and a > best_auc:
            best, best_auc = dict(zip(keys, w)), a
    return best, best_auc


# ---------------------------------------------------------------------------
# 4. Rapport
# ---------------------------------------------------------------------------
def report(df: pd.DataFrame, res: dict, demo: bool):
    line = "=" * 70
    print(f"\n{line}\n  ATLAS BACKTEST" + ("  [DEMO - synthetische data!]" if demo else "") + f"\n{line}")
    a_ = df["ATLAS"].dropna()
    print(f"\n  Periode: {a_.index[0].date()} t/m {a_.index[-1].date()}"
          f"  ({res['n_maanden']} maanden met voldoende dekking)")
    print(f"  Gemiddelde dekking in die periode: "
          f"{df.loc[a_.index, 'dekking'].mean():.0%}")
    print(f"  Basisrate (aandeel pre-crisis maanden): {res['basisrate']:.1%}")

    a = res["auc_totaal"]
    a_s = res.get("auc_streng")
    verdict = ("STERK" if a > 0.8 else "BRUIKBAAR" if a > 0.7
               else "ZWAK" if a > 0.6 else "GEEN SIGNAAL")
    print(f"\n  AUC SOEPEL : {a:.3f}   -> {verdict}")
    print("               (nasleep van crises weggemaskeerd - te makkelijk)")
    if a_s and not np.isnan(a_s):
        v2 = ("STERK" if a_s > 0.8 else "BRUIKBAAR" if a_s > 0.7
              else "ZWAK" if a_s > 0.6 else "GEEN SIGNAAL")
        print(f"\n  AUC STRENG : {a_s:.3f}   -> {v2}   <<< DIT IS HET ECHTE CIJFER")
        print("               (elke maand telt mee, ook de nasleep - zoals in het echt)")
        if a - a_s > 0.10:
            print(f"    !! Verschil van {a - a_s:.2f}. De soepele test vleide het model.")

    print("\n  AUC per pijler (welke pijler doet het werk?):")
    for label, pa in sorted(res["pijler_auc"].items(), key=lambda x: -(x[1] or 0)):
        if pa is not None and not np.isnan(pa):
            print(f"    {label:<24} {pa:.3f}")

    print("\n  AUC PER INDICATOR (>0,5 helpt | <0,5 werkt averechts):")
    print("    soepel  streng   indicator")
    for name, (a, pil, n, a_s) in sorted(res["ind_auc"].items(), key=lambda x: -x[1][3]):
        val = a_s if a_s and not np.isnan(a_s) else 0
        verdict = ("sterk " if val >= 0.70 else
                   "matig " if val >= 0.55 else
                   "ruis  " if val >= 0.45 else
                   "OMGEKEERD")
        ss = f"{a_s:.3f}" if a_s and not np.isnan(a_s) else "  -  "
        print(f"    {a:.3f}   {ss}  {verdict:<9} {name:<32} ({n} mnd)")
    slecht = [n for n, (a, _, _, _) in res["ind_auc"].items() if a < 0.45]
    if slecht:
        print("\n    Deze indicatoren maken het model SLECHTER. Waarschijnlijk")
        print("    zijn het gelijk- of achterlopende signalen (ze reageren op de")
        print("    crisis in plaats van hem aan te kondigen):")
        for n in slecht:
            print(f"      - {n}")

    print(f"\n  HIT RATE (stond ATLAS >={THRESH_FRAGILE} in de {WARN_WINDOW} mnd voor de piek?)")
    print(f"  {'piek':<10} {'gebeurtenis':<28} {'max':>6} {'lead':>6}  oordeel")
    for h in res["hits"]:
        if h.get("status") == "geen data":
            print(f"  {h['piek']:<10} {h['naam'][:28]:<28} {'-':>6} {'-':>6}  geen data")
            continue
        mark = "KRITIEK" if h["kritiek"] else ("hit" if h["hit"] else "GEMIST")
        lead = f"{h['lead_mnd']}m" if h["lead_mnd"] is not None else "-"
        print(f"  {h['piek']:<10} {h['naam'][:28]:<28} {h['max_score_24m']:>6} {lead:>6}  {mark}")

    print(f"\n  BASISTARIEF VAN DE DREMPELS (de eerlijkheidstoets):")
    print(f"    score >=60 in {res['pct_boven_60']:.0%} van ALLE maanden")
    print(f"    score >=80 in {res['pct_boven_80']:.0%} van ALLE maanden")
    if res["pct_boven_60"] > 0.45:
        print("    !! De drempel van 60 wordt zo vaak gehaald dat een 'hit'")
        print("       weinig zegt. De schaal moet strenger.")

    print(f"\n  FALSE POSITIVES (score >={THRESH_CRITICAL}, geen piek binnen {WARN_WINDOW} mnd):")
    print(f"    {res['false_pos_maanden']} maanden"
          + (f" in {', '.join(res['false_pos_periodes'])}" if res["false_pos_periodes"] else " - geen"))

    thin = df.attrs.get("thin", [])
    if thin:
        print("\n  UITGESLOTEN uit de score (historie < 25 jaar, dus hooguit een")
        print("  crisis gezien - hun AUC is anekdote, geen statistiek):")
        for t in thin:
            print(f"    - {t}")

    print("\n  CRISIS-AUTOPSIE - indicatorscore 12 maanden VOOR elke piek:")
    inds = [i.name for i in INDICATORS if i.name in df and i.name not in thin]
    peaks_have = [p for p in PEAKS
                  if (pd.Timestamp(p) - pd.DateOffset(months=12)) >= df.index[0]]
    hdr = "".join(f"{p[:4]:>7}" for p in peaks_have)
    print(f"    {'indicator':<34}{hdr}")
    for name in inds:
        row = ""
        for p in peaks_have:
            t = pd.Timestamp(p) - pd.DateOffset(months=12) + pd.offsets.MonthEnd(0)
            v = df[name].reindex([t]).iloc[0]
            row += f"{v:>7.0f}" if pd.notna(v) else f"{'-':>7}"
        print(f"    {name:<34}{row}")
    print("\n    Lees dit per KOLOM: welke indicatoren stonden aan voor die crisis,")
    print("    en welke sliepen? Een lage kolom betekent dat het model die crisis")
    print("    niet zag - en dan wil je weten waarom.")

    loo = leave_one_out(df)
    print("\n  OVERFIT-TOETS 1 - laat een crisis weg, meet opnieuw:")
    print(f"    {'weggelaten':<12} {'AUC rest':>9}   {'alleen die crisis':>18}")
    for p in loo["zonder"]:
        a_zonder = loo["zonder"][p]
        a_solo = loo["alleen"].get(p)
        z = f"{a_zonder:.3f}" if a_zonder and not np.isnan(a_zonder) else "  -  "
        so = f"{a_solo:.3f}" if a_solo and not np.isnan(a_solo) else "  -  "
        print(f"    {p:<12} {z:>9}   {so:>18}")
    vals = [v for v in loo["alleen"].values() if v and not np.isnan(v)]
    if vals and (max(vals) - min(vals)) > 0.25:
        print("    !! Grote spreiding: het model presteert heel verschillend per")
        print("       crisis. Het heeft geen algemeen patroon geleerd, maar leunt")
        print("       op een of twee gebeurtenissen.")

    oos = out_of_sample(df)
    print("\n  OVERFIT-TOETS 2 - vroege vs late periode:")
    for k, v in oos.items():
        print(f"    {k:<12} AUC {v:.3f}" if v else f"    {k:<12} te weinig data")
    print("    LET OP: dit is GEEN zuivere out-of-sample test. De richtingen van")
    print("    de indicatoren zijn gekozen na inzage in de hele historie.")

    print(f"\n  Volledige reeks weggeschreven naar {HISTORY_CSV}")
    print("\n  LET OP: bij ~5 events is elke AUC statistisch fragiel. Behandel dit")
    print("  als sanity check, niet als bewijs. Echte validatie vergt het")
    print("  landenpanel (Jorda-Schularick-Taylor, 18 landen) - dat is v3.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="data ophalen van FRED en cachen")
    ap.add_argument("--demo", action="store_true", help="synthetische data")
    ap.add_argument("--optimize", action="store_true", help="pijlerwegingen grid-searchen")
    args = ap.parse_args()

    data = load_data(args.fetch, args.demo)
    hist = build_history(data)
    hist.round(1).to_csv(HISTORY_CSV)
    report(hist, evaluate(hist), args.demo)

    if args.optimize:
        print("  Wegingen optimaliseren (grid search)...")
        w, a = optimize_weights(hist)
        print(f"  Beste AUC: {a:.3f} met wegingen:")
        for k, v in w.items():
            print(f"    {PILLARS[k][0]:<24} {v:.0%}   (prior: {PILLARS[k][1]:.0%})")
        print("\n  WAARSCHUWING: in-sample geoptimaliseerd op 5 events. Als deze")
        print("  wegingen sterk afwijken van de priors, is dat vermoedelijk ruis,")
        print("  geen inzicht. Vertrouw de literatuur-priors tenzij het verschil groot")
        print("  EN theoretisch verklaarbaar is.\n")
