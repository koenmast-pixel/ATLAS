# ATLAS – Mapping the Global Financial Cycle
### Advanced Tracking of Long-term Asset Stability
**Scorecard v1.0 — Indicatoren, transformaties, drempels en bronnen**

---

## Methodologie in het kort

Elke indicator krijgt **twee scores**:
1. **Cyclisch (C):** afwijking van langjarige trend via eenzijdige HP-filter (lambda = 400.000, BIS-standaard voor financiële cycli van 15–20 jaar) óf z-score over rollend 15–20 jaar venster.
2. **Seculair (S):** percentiel over de *volledige* beschikbare historie (expanding window). 95e percentiel = hoogste ooit gemeten niveau.

Aggregatie: indicator → pijlerscore (gemiddelde van C en S, na PCA-check op dubbeltelling) → totaalscore 0–100, gewogen per pijler. Wegingen zijn priors op basis van noise-to-signal ratio's uit de literatuur (Kaminsky-Lizondo-Reinhart 1998; Drehmann & Juselius 2014) en worden gevalideerd op de **Jordà-Schularick-Taylor Macrohistory Database** (18 landen, 1870–heden, gratis: macrohistory.net/database).

**Regimes:** 0–40 expansie · 40–60 late cycle · 60–80 fragiel · 80–100 kritiek.
Kalibratiedoel: 1929, 1989 (JP), 2000 en 2007 scoren >80 in de 12–24 maanden vóór de piek, zonder false positives in bijv. 1994, 2011, 2015.

---

## Pijler 1 — Krediet & Liquiditeit (weging 30%)
*Hoogste bewezen voorspelkracht (Schularick & Taylor 2012; Drehmann & Juselius 2014). Lead time: 2–4 jaar (gap), 1–2 jaar (DSR).*

| Indicator | Transformatie | Gevarendrempel | Bron |
|---|---|---|---|
| Credit-to-GDP gap | HP-gap (λ=400k) | > +10 pp | BIS (gratis, per land) |
| 3-jaars reële private kredietgroei | Expanding percentile | > 90e pct | BIS / JST Macrohistory |
| Debt Service Ratio (DSR) | Afwijking van landgemiddelde | > +6 pp | BIS |
| Cross-currency basis (EUR/JPY vs USD) | Rollende z-score | < −2σ (dollarstress) | BIS / Bloomberg |
| Repo-spreads (SOFR–IORB), reserves, RRP | Rollende z-score | Spike > +2σ | FRED |
| Private credit / shadow banking AUM-groei | Expanding percentile | > 90e pct | FSB Global Monitoring Report |

## Pijler 2 — Waardering (weging 20%)
*Voorspelt geen timing, wel de omvang van de val en 10-jaars rendement. Lead time: onbepaald ("markets can stay irrational").*

| Indicator | Transformatie | Gevarendrempel | Bron |
|---|---|---|---|
| Shiller CAPE / Excess CAPE Yield | Expanding percentile | CAPE > 90e pct; ECY < 10e pct | shillerdata.com |
| Market cap / GDP (Buffett-indicator) | HP-trendgecorrigeerd¹ | > +2σ boven trend | FRED (WILL5000 / GDP) |
| Tobin's Q | Expanding percentile | > 90e pct | Fed Z.1 |
| Huizenprijs/inkomen & prijs/huur gap | HP-gap | > +1,5σ | OECD, Dallas Fed Int'l HP DB |
| High-yield kredietspreads (OAS) | Rollende z-score | < −1,5σ (te krap = complacency) | FRED (BAMLH0A0HYM2) |

¹ *Let op seculaire drift door gestegen winstaandeel en globalisering van omzetten — daarom trendcorrectie i.p.v. absolute drempel.*

## Pijler 3 — Monetair & Rente (weging 20%)
*De trigger-pijler: verkrapping ging aan elke grote piek vooraf. Lead time: 12–18 maanden (curve).*

| Indicator | Transformatie | Gevarendrempel | Bron |
|---|---|---|---|
| Yield curve 10y–3m | Niveau | < 0 (inversie), signaal bij re-steepening | FRED (T10Y3M) |
| Reële beleidsrente vs r* (HLW-model) | Verschil | > +1 pp restrictief | NY Fed (Holston-Laubach-Williams) |
| Beleidsrentewijziging, 24 mnd | Niveau | > +200 bp verkrapping | FRED / BIS policy rates |
| Centrale bankbalans (G4), 12-mnd Δ | Rollende z-score | Krimp < −1σ (QT) | FRED, ECB, BoJ |
| Reële M2-groei | Niveau | Negatief (historisch zeldzaam) | FRED |

## Pijler 4 — Gedrag & Marktstructuur (weging 15%)
*Minsky-pijler: stabiliteit kweekt instabiliteit. VIX-logica is omgekeerd: láág is gevaarlijk. Lead time: maanden.*

| Indicator | Transformatie | Gevarendrempel | Bron |
|---|---|---|---|
| VIX-niveau + termijnstructuur | Rollende z-score | VIX < 13 + steile contango | CBOE / FRED (VIXCLS) |
| Margin debt / GDP | Expanding percentile | > 90e pct + omslag in groei | FINRA (maandelijks) |
| Aandelenallocatie huishoudens | Expanding percentile | > 90e pct² | Fed Z.1 |
| IPO-volume + % verlieslatende IPO's | Expanding percentile | > 90e pct | Jay Ritter IPO-data (U. Florida) |
| Sentiment (II bull/bear, put/call, AAII) | Rollende z-score | > +2σ bullish | Investors Intelligence, CBOE, AAII |
| Passief aandeel + 0DTE-optievolume | Niveau (structureel) | Kwalitatieve modifier³ | ICI, CBOE |

² *Sterkste bekende voorspeller van 10-jaars aandelenrendement (Philosophical Economics 2013).*
³ *Te korte historie voor percentielen; gebruik als fragiliteits-multiplier op de pijlerscore.*

## Pijler 5 — Geopolitiek & Maatschappij (weging 15%)
*Traagste variabelen; bepalen de seculaire context (1929-parallel), niet de timing.*

| Indicator | Transformatie | Gevarendrempel | Bron |
|---|---|---|---|
| Top-1% vermogens-/inkomensaandeel | Expanding percentile | > 90e pct | World Inequality Database (wid.world) |
| Populisme-stemaandeel | Expanding percentile | > 90e pct | Funke-Schularick-Trebesch dataset; V-Dem |
| Geopolitical Risk Index (GPR) | Rollende z-score | > +1,5σ aanhoudend | Caldara & Iacoviello (matteoiacoviello.com) |
| Protectionisme / handelsinterventies | 3-jaars trend | Sterk stijgend | Global Trade Alert |
| Reservemunt-dominantie USD | Seculaire trend | Dalende trend = context | IMF COFER |

---

## Wegingsonderbouwing (priors)

| Pijler | Weging | Kernbron |
|---|---|---|
| Krediet & Liquiditeit | 30% | Drehmann & Juselius (2014): credit gap en DSR hoogste AUC (~0,75–0,85) van alle early-warning indicatoren |
| Waardering | 20% | Campbell & Shiller (1998); voorspelt omvang, niet timing |
| Monetair | 20% | Estrella & Mishkin (1998): curve beste 12-mnd recessievoorspeller |
| Gedrag | 15% | Minsky (1986); Baron & Xiong (2017): lage vol + kredietboom = crashrisico |
| Geopolitiek/Sociaal | 15% | Funke, Schularick & Trebesch (2016); context, geen timing |

**Validatie:** bereken per indicator de AUC (area under ROC-curve) op de JST-database met crisis-dummies. Herweeg naar rato van (AUC − 0,5). Test out-of-sample: kalibreer op pre-1990, valideer op 2000/2007.

## Bekende beperkingen
1. **n is klein.** Vier à vijf events in één land; het landenpanel (JST) is de enige remedie.
2. **Timing blijft onvoorspelbaar.** ATLAS meet *fragiliteit*, niet de datum. Een score van 85 kan 3 jaar op 85 blijven staan.
3. **Regime-verandering.** Centrale banken reageren nu anders dan in 1929; passief beleggen en private credit bestaan pas kort. Elke crisis breekt op een nieuwe plek.
4. **Data-revisies.** Gebruik real-time vintages (ALFRED) waar mogelijk, anders overschat je de historische voorspelkracht.

## Roadmap
- **v1:** scorecard handmatig vullen (kwartaal), VS + wereld-aggregaat
- **v2:** automatische data-pipeline (FRED API, BIS-downloads), backtest 1970–heden
- **v3:** Markov-switching regimemodel + dashboard met pijler-drilldown
