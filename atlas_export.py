#!/usr/bin/env python3
"""
ATLAS export - schrijft atlas_data.json voor het dashboard.

Draait de pipeline en exporteert huidige stand + pijlers + indicatoren +
volledige maandhistorie naar een JSON die de React-frontend inleest.

Gebruik:
    export FRED_API_KEY=...
    python atlas_export.py --fetch            # data ophalen + exporteren
    python atlas_export.py                    # exporteren vanaf cache
    python atlas_export.py --demo             # synthetische data (test)
    python atlas_export.py -o public/atlas_data.json

Draait in CI (GitHub Actions) volledig headless.
"""

from __future__ import annotations  # Python 3.9-compatibel

import argparse
import json
from datetime import date, datetime

import numpy as np
import pandas as pd

from atlas import INDICATORS, PILLARS, REGIMES, score_series
from atlas_backtest import (load_data, build_history, PEAKS, EXOGENOUS,
                            evaluate, leave_one_out)

# ---------------------------------------------------------------------
#  DE UITKOMST VAN DE ECHTE VALIDATIE.
#  Vast ingebakken, want het JST-panel (18 landen, 61 bankencrises) vergt een
#  Excel-bestand van macrohistory.net dat niet in CI beschikbaar is. Deze
#  cijfers komen uit atlas_jst.py en atlas_gauge.py; draai die opnieuw als het
#  model verandert.
#
#  Het VS-cijfer (0,90) is IN-SAMPLE en dus opgeblazen. Het JST-cijfer (0,68)
#  is out-of-sample: geen enkele parameter is op die data afgesteld. Dat is het
#  getal dat op het dashboard hoort te staan, niet het vleiende.
# ---------------------------------------------------------------------
JST = {
    "auc_streng": 0.680,
    "auc_vs_insample": 0.904,
    "landen": 18,
    "landjaren": 1997,
    "crises": 61,
    "basisrate": 0.06,
    "drempels": [
        {"band": "0-40",   "j3": 0.05, "j5": 0.11, "j10": 0.19, "jaren": 619},
        {"band": "40-60",  "j3": 0.06, "j5": 0.11, "j10": 0.23, "jaren": 833},
        {"band": "60-70",  "j3": 0.12, "j5": 0.20, "j10": 0.31, "jaren": 298},
        {"band": "70-80",  "j3": 0.22, "j5": 0.26, "j10": 0.45, "jaren": 186},
        {"band": "80-100", "j3": 0.33, "j5": 0.43, "j10": 0.54, "jaren": 61},
    ],
    "alle_jaren": {"j3": 0.09, "j5": 0.15, "j10": 0.26, "jaren": 1997},
    "mediaan_percentiel": 82,
}

BRONNEN = [
    {"naam": "FRED (Federal Reserve Bank of St. Louis)",
     "wat": "krediet, geldhoeveelheid, rente, huizenprijzen, margin debt, "
            "aandelenallocatie, consumentenvertrouwen",
     "url": "https://fred.stlouisfed.org"},
    {"naam": "Robert Shiller, Yale",
     "wat": "CAPE, Excess CAPE Yield, reele koers en totaalrendement sinds 1871",
     "url": "https://shillerdata.com"},
    {"naam": "Jorda-Schularick-Taylor Macrohistory Database",
     "wat": "18 landen, 1870-2020, 61 bankencrises - hiermee is ATLAS-KREDIET "
            "out-of-sample getoetst",
     "url": "https://www.macrohistory.net/database/"},
    {"naam": "BIS",
     "wat": "credit-to-GDP (via FRED)",
     "url": "https://www.bis.org/statistics/"},
]


def regime_for(score: float) -> str:
    return next(name for cap, name in REGIMES if score < cap)


def clean(v):
    """NaN/numpy -> JSON-veilige waarden."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.floating, np.integer)):
        return round(float(v), 1)
    if isinstance(v, float):
        return round(v, 1)
    return v


def export(data: dict, outfile: str) -> dict:
    hist = build_history(data)
    labels = {k: PILLARS[k][0] for k in PILLARS}

    # DE LAATSTE MAAND IS NIET DE BESTE MAAND.
    # Kwartaalreeksen (margin debt, Buffett, aandelenallocatie, kredietgap) lopen
    # maanden achter op de dagreeksen. De allerlaatste maand heeft daardoor soms
    # maar de helft van de indicatoren - en dan toont het dashboard een cijfer
    # dat op een half model rust. Dat is erger dan geen cijfer, want het ziet er
    # even gezaghebbend uit. Dus: pak de laatste maand met voldoende dekking.
    MIN_DEKKING = 0.70
    genoeg = hist[hist["dekking"] >= MIN_DEKKING]["ATLAS"].dropna()
    valid = genoeg if not genoeg.empty else hist["ATLAS"].dropna()
    if valid.empty:
        raise SystemExit("Geen ATLAS-score berekend - check of de data binnenkwam.")
    last_date = valid.index[-1]
    last_score = float(valid.iloc[-1])

    achterstand = int((hist["ATLAS"].dropna().index[-1].to_period("M")
                       - last_date.to_period("M")).n)

    # --- pijlers (huidige stand + 12-mnd verandering) ---
    pillars = []
    for key, (label, weight) in PILLARS.items():
        col = hist[label].dropna()
        cur = float(col.iloc[-1]) if not col.empty else None
        prev = float(col.iloc[-13]) if len(col) > 13 else None
        pillars.append({
            "key": key, "label": label, "weight": weight,
            "score": clean(cur),
            "delta12m": clean(cur - prev) if (cur is not None and prev is not None) else None,
        })

    # --- indicatoren: laatste cyclische/seculaire/gecombineerde score ---
    indicators = []
    for ind in INDICATORS:
        if ind.name not in data:
            indicators.append({"name": ind.name, "pillar": ind.pillar,
                               "score": None, "error": "geen data"})
            continue
        ss, err = score_series(data[ind.name], ind)
        if ss is None or ss.dropna().empty:
            indicators.append({"name": ind.name, "pillar": ind.pillar,
                               "score": None, "error": err or "geen reeks"})
            continue
        s = ss.dropna()
        indicators.append({
            "name": ind.name, "pillar": ind.pillar,
            "series_id": ", ".join(ind.series), "transform": ind.transform,
            "direction": ind.direction, "note": ind.note,
            "score": clean(float(s.iloc[-1])),
            "per": str(s.index[-1].date()),
        })

    # --- historie (maandelijks, alleen rijen met een score) ---
    history = []
    volledig = hist[hist["dekking"] >= MIN_DEKKING]
    for dt, row in volledig.dropna(subset=["ATLAS"]).iterrows():
        rec = {"date": dt.strftime("%Y-%m-%d"), "atlas": clean(row["ATLAS"]),
               "ruw": clean(row.get("ATLAS_ruw"))}
        for key, label in labels.items():
            rec[key] = clean(row.get(label))
        history.append(rec)

    # Validatie meesturen. Een dashboard dat zijn score toont maar niet zijn
    # betrouwbaarheid, is misleidend.
    try:
        ev = evaluate(hist)
        loo = leave_one_out(hist)
        validation = {
            "auc": clean(ev.get("auc_totaal")),
            "per_crisis": [
                {"date": p, "label": PEAKS[p], "auc": clean(v)}
                for p, v in loo["alleen"].items() if v is not None
            ],
            "pct_boven_60": ev.get("pct_boven_60"),
            "false_positives": ev.get("false_pos_maanden"),
        }
    except Exception as e:
        validation = {"error": str(e)}

    # ---------------- ATLAS-ZEEPBEL en ATLAS-EUFORIE ----------------
    zeepbel, euforie = None, None
    try:
        import atlas_equity as eq
        zeepbel = eq.export_payload(data)
    except Exception as e:
        zeepbel = {"error": str(e)}
    try:
        import atlas_euforie as ef
        euforie = ef.export_payload(data)
    except Exception as e:
        euforie = {"error": str(e)}

    payload = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "validation": validation,
        "jst": JST,
        "bronnen": BRONNEN,
        "zeepbel": zeepbel,
        "euforie": euforie,
        "current": {
            "score": round(last_score, 1),
            "regime": regime_for(last_score),
            "date": str(last_date.date()),
            "coverage": clean(float(hist.loc[last_date, "dekking"])),
            "maanden_achterstand": achterstand,
            "min_dekking": MIN_DEKKING,
        },
        "pillars": pillars,
        "indicators": indicators,
        "history": history,
        "peaks": [{"date": d, "label": l} for d, l in PEAKS.items()]
               + [{"date": d, "label": l, "exogenous": True} for d, l in EXOGENOUS.items()],
        "regimes": [{"max": c, "label": n} for c, n in REGIMES],
    }

    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("-o", "--out", default="atlas_data.json")
    args = ap.parse_args()

    d = load_data(args.fetch, args.demo)
    p = export(d, args.out)
    c = p["current"]
    print(f"\n  {args.out} geschreven")
    print(f"  Stand per {c['date']}: {c['score']} -> {c['regime']}"
          f"  (dekking {c['coverage']})")
    print(f"  Historie: {len(p['history'])} maanden, "
          f"{p['history'][0]['date']} t/m {p['history'][-1]['date']}\n")
