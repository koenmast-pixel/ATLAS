#!/usr/bin/env python3
"""
ATLAS-EUFORIE — hoe ver zitten we in de speculatieve fase?

DIT IS GEEN VOORSPELLER. Lees dat nog een keer.

Een crashvoorspeller beweert iets over de toekomst, en zo'n bewering moet je
toetsen. Dat kan hier niet: er zijn maar vier bruikbare beurscrashes sinds 1960.
Elke AUC daarop is ruis met drie decimalen.

Deze meter beweert niets over de toekomst. Hij MEET een toestand:
hoeveel hefboom, hoeveel particuliere inleg, hoe duur, hoe snel stijgend -
allemaal afgezet tegen de eigen geschiedenis. Dat is een thermometer, geen alarm.
Een thermometer hoef je niet te valideren tegen het aantal keer dat iemand
koorts kreeg; hij moet gewoon de temperatuur goed aflezen.

Wat je ermee kunt: zien of 2026 heter is dan 2010, en hoe het zich verhoudt tot
1968, 2000 en 2007. Wat je er NIET mee kunt: het moment bepalen. Een markt kan
jaren op 90 blijven staan. Japan stond in 1987 op zijn hoogste stand en de
bankencrisis kwam in 1997 - tien jaar later.

    WEGING (op verzoek: margin debt het zwaarst)
      35%  Margin debt / BBP              - geleend geld is de brandstof
      25%  Aandelenallocatie huishoudens  - wie zit er in de markt?
      25%  Waardering (CAPE + ECY)        - wat betaal je?
      15%  Koersversnelling               - hoe hard gaat het nog?
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from atlas_backtest import load_data
from atlas_shiller import shiller_series

RUW = ["Margin debt / BBP", "Aandelenallocatie huishoudens"]

MIN_HIST = 240          # 20 jaar voordat een percentiel iets betekent
SMOOTH = 6              # 6-maands gemiddelde: ruis eruit, regime erin


# ----------------------------------------------------------------------
#  De vier componenten
# ----------------------------------------------------------------------
COMPONENTEN = {
    "Margin debt / BBP":              0.35,
    "Aandelenallocatie huishoudens":  0.25,
    "Waardering (CAPE + ECY)":        0.25,
    "Koersversnelling":               0.15,
}


def pit_percentiel(s: pd.Series, min_hist: int = MIN_HIST) -> pd.Series:
    """Percentiel t.o.v. de EIGEN GESCHIEDENIS TOT DAN TOE (point-in-time).

    Cruciaal: geen kennis van de toekomst. De stand van 1995 wordt beoordeeld
    met de ogen van 1995, niet met die van nu. Anders zou je in 1995 al 'weten'
    dat 2000 hoger zou worden, en dat vertekent alles.

    Gevolg: een nieuwe recordstand levert altijd 100 op. Dat is geen fout -
    dat IS wat een record betekent.
    """
    return 100 * s.expanding(min_periods=min_hist).rank(pct=True)


def afwijking_van_trend(s: pd.Series, lam: float = 400_000,
                        min_obs: int = 40) -> pd.Series:
    """Hoe ver staat deze reeks boven zijn eigen LANGE trend?

    TWEE VALKUILEN, allebei hier omzeild:

    (1) KAAL NIVEAU MEET DRIFT, GEEN EUFORIE.
        Margin debt en aandelenallocatie zijn structureel gestegen: meer
        hefboom, ETF's, brokerapps. Een percentiel van het niveau staat daardoor
        sinds 1995 permanent op 90+ - niet omdat het altijd manie is, maar omdat
        elk jaar hoger is dan bijna alles ervoor. Versie 1 riep 1997-1998 uit tot
        heetste periode ooit en negeerde 2000 en 2021. Een thermometer die dertig
        jaar koorts aanwijst is stuk.

    (2) EEN TIENJAARSGEMIDDELDE EET DE ZEEPBEL OP.
        Versie 2 gebruikte een 10-jaars voortschrijdend gemiddelde als trend.
        Gevolg: in 2000 stond margin debt al vijf jaar hoog, dus de 'trend' was
        meegekropen en de afwijking werd klein. De dotcom-piek scoorde 66 terwijl
        1997 op 91 stond. Het model had de manie genormaliseerd tot het nieuwe
        normaal - precies de fout die je in een zeepbelmeter niet wilt maken.

    De oplossing is hetzelfde gereedschap dat de BIS gebruikt voor de kredietgap:
    een eenzijdig HP-filter met een ZEER hoge lambda (400.000). Dat levert een
    trend op die zich bewust NIET aanpast aan een opbouw van vijf tot tien jaar.
    Eenzijdig = op elk moment alleen met de data tot dan toe; geen blik vooruit.
    """
    from statsmodels.tsa.filters.hp_filter import hpfilter

    s = s.dropna()
    uit = pd.Series(index=s.index, dtype=float)
    for i in range(min_obs, len(s) + 1):
        cyclus, _ = hpfilter(s.iloc[:i], lamb=lam)
        uit.iloc[i - 1] = cyclus.iloc[-1]        # alleen het LAATSTE punt telt
    return uit


def koersversnelling(p: pd.Series) -> pd.Series:
    """Gaat de markt hard, en gaat hij HARDER dan hij gewend was?

    DE FOUT DIE HIER EERST IN ZAT, want hij is leerzaam:
    ik nam 'laatste jaar MIN de tienjaarstrend'. In maart 2000 zat die
    tienjaarstrend vol met de hele jaren negentig. Je trok dus een decennium
    hausse af van het laatste jaar - en dan lijkt de top van de langste
    bullmarkt ooit een VERTRAGING. De dotcom-piek scoorde 21 van de 100 terwijl
    alle andere componenten op 99 stonden. De maat strafte lange stijgingen af.

    Nu drie stukken, elk als percentiel:
      - het reele 12-maandsrendement          (gaat het hard?)
      - het reele 24-maandsrendement          (is het een aanhoudende run?)
      - het laatste jaar t.o.v. de VIER JAAR DAARVOOR (versnelt het echt?)
        Die vier jaar zijn kort genoeg om niet de hele cyclus op te slokken,
        en lang genoeg om een normaal tempo vast te stellen.

    EERLIJKE KANTTEKENING: dit is S&P-data (Shiller). De melt-up van 1999-2000
    zat grotendeels in de NASDAQ, niet in de brede index. Het reele
    12-maandsrendement van de S&P was tot september 1997 zo'n +35%, en tot maart
    2000 maar zo'n +14%. Op deze bron WAS 1997 dus sneller. Dat is geen bug -
    dat is een grens van de data. Een deel van wat je zoekt is hier onzichtbaar.
    """
    r12 = p.pct_change(12) * 100
    r24 = (1 + p.pct_change(24)) ** 0.5 * 100 - 100          # op jaarbasis
    basis4 = ((p.shift(12) / p.shift(60)) ** 0.25 - 1) * 100  # 4 jaar VOOR het
    versnelling = r12 - basis4                                # laatste jaar

    delen = [pit_percentiel(x, min_hist=120) for x in (r12, r24, versnelling)]
    return pd.concat(delen, axis=1).mean(axis=1, skipna=True)


def bouw_euforie(data: dict) -> tuple[pd.Series, pd.DataFrame]:
    """data = de RUWE reeksen uit load_data (niet de geijkte scores).

    Bewust ruw: ik wil zelf het point-in-time percentiel bepalen, en niet
    bovenop een al geijkte score nog eens een percentiel leggen. Dat laatste
    was precies de bug die de zeepbelmeter eerder de nek omdraaide.
    """
    delen = {}

    niveaus = {}
    for naam in RUW:
        if naam not in data:
            continue
        # Deze reeksen komen uit de Flow of Funds en zijn KWARTAALdata. Het HP-
        # filter draait dus op kwartalen (zoals de BIS bij de kredietgap), en
        # wordt daarna naar maanden uitgesmeerd.
        kw = data[naam].resample("QE").last().dropna()
        gap = afwijking_van_trend(kw)
        gap_m = gap.resample("ME").last().ffill(limit=3)
        niv_m = kw.resample("ME").last().ffill(limit=3)

        niveaus[naam] = pit_percentiel(niv_m)          # kaal niveau (= drift)
        delen[naam] = pit_percentiel(gap_m)            # exces boven lange trend

    # Waardering: CAPE en ECY samen. ECY telt mee omdat 'duur' iets anders
    # betekent bij 1% rente dan bij 8% rente. CAPE alleen zou 2021 en 1929
    # gelijkstellen, terwijl de obligatiemarkt in die twee jaren onvergelijkbaar was.
    # Waardering blijft op NIVEAU. Dure markt is dure markt - CAPE heeft geen
    # structurele drift die je moet wegfilteren (of je moet geloven dat 'deze
    # keer is het anders', en dat is nou net de aanname die je niet wilt maken).
    cape = pit_percentiel(shiller_series("CAPE").resample("ME").last())
    ecy = 100 - pit_percentiel(shiller_series("ECY").resample("ME").last())  # laag = duur
    delen["Waardering (CAPE + ECY)"] = pd.concat([cape, ecy], axis=1).mean(axis=1)
    niveaus["Waardering (CAPE + ECY)"] = delen["Waardering (CAPE + ECY)"]

    prijs = shiller_series("REALPRICE").resample("ME").last()
    delen["Koersversnelling"] = koersversnelling(prijs)     # al een percentiel
    niveaus["Koersversnelling"] = delen["Koersversnelling"]

    comp = pd.DataFrame(delen).sort_index()
    niv = pd.DataFrame(niveaus).sort_index()

    # gewogen gemiddelde over de componenten die er zijn
    w = pd.Series(COMPONENTEN)
    aanwezig = comp.notna()
    gewicht = aanwezig.mul(w, axis=1)
    euforie = (comp.fillna(0) * gewicht).sum(axis=1) / gewicht.sum(axis=1)
    euforie = euforie.where(aanwezig.sum(axis=1) >= 3)     # min. 3 van de 4

    # dezelfde weging op de kale niveaus, puur ter vergelijking
    aanw2 = niv.notna()
    g2 = aanw2.mul(w, axis=1)
    niveau = ((niv.fillna(0) * g2).sum(axis=1) / g2.sum(axis=1)
              ).where(aanw2.sum(axis=1) >= 3)

    return euforie.dropna(), comp, niveau.dropna()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()

    data = load_data(fetch=a.fetch, demo=False)
    ontbreekt = [n for n in RUW if n not in data]
    if ontbreekt:
        raise SystemExit(f"Niet in de cache: {ontbreekt}\n"
                         f"  Draai eerst: python3 atlas_euforie.py --fetch")
    euforie, comp, niveau = bouw_euforie(data)

    print("\n" + "=" * 68)
    print("  ATLAS-EUFORIE — hoe ver in de speculatieve fase?")
    print("=" * 68)
    print("\n  Dit MEET een toestand. Het VOORSPELT niets. Zie de kop van dit")
    print("  bestand voor waarom dat onderscheid alles uitmaakt.\n")
    print(f"  Periode: {euforie.index[0]:%Y-%m} t/m {euforie.index[-1]:%Y-%m}")

    # ---------------- de stand van vandaag ----------------
    t = euforie.index[-1]
    print(f"\n  STAND {t:%B %Y}: {euforie.iloc[-1]:.0f} / 100\n")
    print(f"    {'component':<32}{'stand':>7}{'weging':>9}{'bijdrage':>10}")
    print("    " + "-" * 57)
    for naam, w in COMPONENTEN.items():
        v = comp[naam].loc[:t].dropna()
        if len(v) == 0:
            continue
        v = v.iloc[-1]
        print(f"    {naam:<32}{v:>7.0f}{w:>8.0%}{v * w:>10.1f}")

    # ---------------- het traject ----------------
    print("\n  TRAJECT — is 2026 heter dan 2010?\n")
    print("    'niveau'   = percentiel van de KALE stand   -> meet vooral DRIFT")
    print("    'euforie'  = percentiel van de AFWIJKING VAN TREND -> meet EXCES\n")
    # MAXIMUM binnen het jaar, niet de decemberstand. De piek van 2000 lag in
    # maart; in december was de klap al begonnen en stond de meter weer laag.
    # 'Last' toonde daardoor 75 waar de werkelijke piek 88 was - je mist precies
    # het moment dat je zoekt.
    jaar = euforie.resample("YE").max()
    jaarniv = niveau.resample("YE").max()
    print(f"    {'jaar':<7}{'niveau':>8}{'euforie':>9}")
    for d, v in jaar.items():
        if d.year < 1995:
            continue
        n = jaarniv.get(d, float("nan"))
        bar = "#" * int(v / 2.5) if pd.notna(v) else ""
        merk = "  <<< NU" if d.year == t.year else ""
        print(f"    {d.year:<7}{n:>8.0f}{v:>9.1f}  {bar:<36}{merk}")

    # ---------------- de heetste momenten ooit ----------------
    print("\n  DE TIEN HEETSTE MAANDEN SINDS 1970:\n")
    top = euforie.loc["1970":].nlargest(10)
    for d, v in top.items():
        print(f"    {d:%Y-%m}   {v:5.1f}")

    print("\n  Staan daar clusters rond 1968, 2000, 2021 en nu, dan meet de")
    print("  thermometer wat hij hoort te meten. Staat er iets willekeurigs")
    print("  tussen, dan klopt er iets niet.")

    # ---------------- wat volgde er historisch op? ----------------
    tr = shiller_series("REALTR").resample("ME").last()
    fwd = ((tr.shift(-120) / tr) ** (1 / 10) - 1).reindex(euforie.index) * 100

    print("\n  WAT VOLGDE ER OP EEN HETE MARKT?")
    print("  (reeel totaalrendement over de volgende 10 jaar, per jaar)\n")
    print(f"    {'euforie':<12}{'mediaan':>9}{'slechtste':>11}{'kans <0%':>10}{'mnd':>7}")
    print("    " + "-" * 49)
    for lo, hi in [(0, 40), (40, 60), (60, 75), (75, 90), (90, 101)]:
        m = (euforie >= lo) & (euforie < hi) & fwd.notna()
        if m.sum() < 12:
            continue
        f = fwd[m]
        print(f"    {f'{lo}-{min(hi,100)}':<12}{f.median():>8.1f}%"
              f"{f.min():>10.1f}%{(f < 0).mean():>9.0%}{m.sum():>7}")

    print("\n  LET OP - dit is beschrijvend, niet voorspellend. De bovenste rijen")
    print("  bevatten weinig ONAFHANKELIJKE episodes; overlappende tienjaars-")
    print("  vensters uit dezelfde periode tellen hier als losse maanden mee.")
    print("  Lees het als 'zo zag het eruit', niet als 'zo gaat het worden'.")

    uit = pd.DataFrame({"euforie": euforie}).join(comp)
    uit.to_csv("atlas_euforie.csv")
    print("\n  -> atlas_euforie.csv\n")


if __name__ == "__main__":
    main()


# ----------------------------------------------------------------------
#  Voor het dashboard
# ----------------------------------------------------------------------
def export_payload(data: dict) -> dict:
    """Levert de euforiemeter aan atlas_export.py."""
    euforie, comp, niveau = bouw_euforie(data)
    tr = shiller_series("REALTR").resample("ME").last()
    fwd = ((tr.shift(-120) / tr) ** (1 / 10) - 1).reindex(euforie.index) * 100

    payoff = []
    for lo, hi in [(0, 40), (40, 60), (60, 75), (75, 90), (90, 101)]:
        m = (euforie >= lo) & (euforie < hi) & fwd.notna()
        if m.sum() < 12:
            continue
        f = fwd[m]
        payoff.append({"band": f"{lo}-{min(hi, 100)}",
                       "mediaan": round(float(f.median()), 1),
                       "slechtste": round(float(f.min()), 1),
                       "kans_verlies": round(float((f < 0).mean()), 2),
                       "maanden": int(m.sum())})

    jaar = euforie.resample("YE").max()
    t = euforie.index[-1]
    return {
        "score": round(float(euforie.iloc[-1]), 1),
        "datum": str(t.date()),
        "componenten": [
            {"naam": n, "stand": round(float(comp[n].loc[:t].dropna().iloc[-1]), 0),
             "weging": w}
            for n, w in COMPONENTEN.items()
            if n in comp and comp[n].loc[:t].notna().any()
        ],
        "traject": [{"jaar": int(d.year), "score": round(float(v), 1)}
                    for d, v in jaar.items() if pd.notna(v)],
        "payoff": payoff,
        "top": [{"maand": f"{d:%Y-%m}", "score": round(float(v), 1)}
                for d, v in euforie.loc["1970":].nlargest(8).items()],
    }
