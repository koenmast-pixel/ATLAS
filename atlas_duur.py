# atlas_duur.py — helpt de DUUR van hoge waardering en de RUN-UP-snelheid
# bij het inschatten van aandelencrashes? Getoetst op het JST-panel.
import sys
import numpy as np
import pandas as pd
from pathlib import Path

LOCAL     = ["JSTdatasetR6.xlsx", "JSTdatasetR5.xlsx", "JSTdataset.xlsx", "jst.xlsx"]
MIN_HIST  = 20     # jaren historie nodig voor het eenzijdige percentiel
HOOG_PCT  = 80     # 'hoog' = waardering boven dit eenzijdige percentiel
CRASH_DAL = 0.30   # reele daling van >30% ...
CRASH_JR  = 3      # ... binnen 3 jaar na de piek

def load_jst():
    for f in LOCAL:
        if Path(f).exists():
            try:
                df = pd.read_excel(f, sheet_name="Data")
            except ValueError:
                df = pd.read_excel(f)
            print(f"  JST gelezen uit lokaal bestand: {f}")
            return df
    sys.exit("JST-bestand niet gevonden in deze map.")

def eenzijdig_pct(s):
    vals = s.values.astype(float)
    out = np.full(len(vals), np.nan)
    for i in range(len(vals)):
        hist = vals[:i+1]
        hist = hist[~np.isnan(hist)]
        if len(hist) >= MIN_HIST and not np.isnan(vals[i]):
            out[i] = 100.0 * (hist <= vals[i]).mean()
    return pd.Series(out, index=s.index)

def auc(score, label):
    d = pd.DataFrame({"s": score, "y": label}).dropna()
    pos = d[d.y == 1].s.values
    neg = d[d.y == 0].s.values
    if len(pos) < 5 or len(neg) < 5:
        return np.nan
    ranks = pd.Series(np.concatenate([pos, neg])).rank().values
    return (ranks[:len(pos)].sum() - len(pos)*(len(pos)+1)/2) / (len(pos)*len(neg))

def per_land(g):
    g = g.sort_values("year").set_index("year")
    infl = g["cpi"].pct_change()
    capg = g["eq_capgain"] if "eq_capgain" in g else g["eq_tr"] - g["eq_dp"]
    if capg.isna().all():
        capg = g["eq_tr"] - g["eq_dp"]
    rret = (1 + capg) / (1 + infl) - 1
    lr = np.log1p(rret)
    idx = np.exp(lr.fillna(0).cumsum())          # reele prijsindex
    idx[lr.isna()] = np.nan                       # gaten (oorlog) niet vertrouwen

    out = pd.DataFrame(index=g.index)
    out["idx"]    = idx
    out["val"]    = 1.0 / g["eq_dp"]              # prijs/dividend = waardering
    out["pct"]    = eenzijdig_pct(out["val"])
    hoog          = out["pct"] >= HOOG_PCT
    out["duur"]   = hoog.groupby((~hoog).cumsum()).cumsum().where(hoog, 0)
    out["runup2"] = idx.pct_change(2) * 100

    # crashpieken: daling start en reeel dal >30% binnen CRASH_JR jaar
    crash = pd.Series(0, index=g.index)
    laatste = -99
    for t in g.index:
        v = idx.get(t, np.nan)
        if np.isnan(v) or t - laatste <= CRASH_JR:
            continue
        fut = idx.reindex(range(t+1, t+CRASH_JR+1)).dropna()
        if len(fut) and fut.iloc[0] < v and fut.min() < (1-CRASH_DAL)*v:
            crash[t] = 1
            laatste = t
    out["crash"] = crash
    for n in (1, 2, 3):
        out[f"pre{n}"] = 0
        for t in g.index[crash == 1]:
            out.loc[(out.index >= t-n) & (out.index < t), f"pre{n}"] = 1
    return out

def kans(d, mask, kol):
    sel = d[mask & d[kol].notna()]
    return (100*sel[kol].mean() if len(sel) else np.nan), len(sel)

def main():
    df = load_jst()
    delen = []
    for land, g in df.groupby("country"):
        try:
            p = per_land(g)
            p["land"] = land
            delen.append(p)
        except Exception:
            pass
    d = pd.concat(delen)
    d = d[d["pct"].notna()]

    n_crash = int(d["crash"].sum())
    print("\n" + "="*68)
    print("  DUUR & RUN-UP — de waarderingsklok-toets (JST, 18 landen)")
    print("="*68)
    print(f"\n  {len(d)} landjaren met waarderingspercentiel | {n_crash} aandelencrashes")
    print(f"  (crash = reeel >{int(CRASH_DAL*100)}% omlaag binnen {CRASH_JR} jaar; "
          f"eigen datering,\n   dus telling kan afwijken van atlas_events.py)")

    print("\n  AUC per kenmerk (crash binnen 2 jaar):")
    for naam, kol in [("Waarderingspercentiel", "pct"),
                      ("Duur boven 80e pct   ", "duur"),
                      ("Run-up 2 jaar        ", "runup2")]:
        print(f"    {naam}  {auc(d[kol], d['pre2']):.3f}")

    print("\n  KANS OP CRASH, geconditioneerd  (kolommen: <1jr, <2jr, <3jr, n):")
    conds = [
        ("alle jaren (basisrate)",        pd.Series(True, index=d.index)),
        ("waardering >= 80e pct",         d["pct"] >= 80),
        ("  ... en duur >= 3 jr",         (d["pct"] >= 80) & (d["duur"] >= 3)),
        ("  ... en duur >= 6 jr",         (d["pct"] >= 80) & (d["duur"] >= 6)),
        ("run-up 2jr >= 50%",             d["runup2"] >= 50),
        ("hoog EN run-up >= 50%",         (d["pct"] >= 80) & (d["runup2"] >= 50)),
        ("hoog, VERS (duur<=2) en run-up",(d["pct"] >= 80) & (d["duur"] <= 2) & (d["runup2"] >= 50)),
    ]
    for naam, m in conds:
        cel = []
        for n in (1, 2, 3):
            k, cnt = kans(d, m, f"pre{n}")
            cel.append(f"{k:5.1f}%" if not np.isnan(k) else "    - ")
        print(f"    {naam:34s} {cel[0]} {cel[1]} {cel[2]}   n={int(m.sum())}")

    print("\n  DE KERNVRAAG — gegeven hoge waardering: telt de DUUR als klok?")
    print("  (kans op crash binnen 2 jaar per duur-emmer)")
    for lo, hi, lbl in [(1,2,"1-2 jr hoog"), (3,5,"3-5 jr hoog"),
                        (6,10,"6-10 jr hoog"), (11,99,">10 jr hoog")]:
        m = (d["duur"] >= lo) & (d["duur"] <= hi)
        k, cnt = kans(d, m, "pre2")
        s = f"{k:5.1f}%" if not np.isnan(k) else "    - "
        print(f"    {lbl:14s} {s}   ({cnt} landjaren)")

    print("\n  AUTOPSIE — stand in het jaar VOOR elke crash:")
    print(f"    {'land':<14s}{'crash':>6s}{'pct':>7s}{'duur':>6s}{'run-up2j':>10s}")
    rows = d[d["crash"] == 1]
    for t, r in rows.iterrows():
        vorig = d[(d["land"] == r["land"]) & (d.index == t-1)]
        if len(vorig):
            v = vorig.iloc[0]
            ru = f"{v['runup2']:.0f}%" if not np.isnan(v["runup2"]) else "-"
            pc = f"{v['pct']:.0f}" if not np.isnan(v["pct"]) else "-"
            print(f"    {r['land']:<14s}{t:>6d}{pc:>7s}{int(v['duur']):>6d}{ru:>10s}")

    d.to_csv("atlas_duur.csv")
    print("\n  -> atlas_duur.csv")
    print("\n  LEESWIJZER: vergelijk elke rij met de basisrate. Alleen een")
    print("  verhouding die duidelijk boven de basisrate ligt EN op een")
    print("  behoorlijke n rust, telt. Duur-emmers die NIET oplopen = de")
    print("  'hoe langer hoog, hoe gevaarlijker'-hypothese faalt.")

if __name__ == "__main__":
    main()
