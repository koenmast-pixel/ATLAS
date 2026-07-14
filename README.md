# ATLAS — Mapping the Global Financial Cycle
### Advanced Tracking of Long-term Asset Stability

Een dashboard dat meet **waar de economie in de lange financiële cyclus staat** —
niet wanneer er iets breekt, maar hoe ondiep het water is.

---

## Architectuur

```
GitHub Actions (elke maandag, key in Secrets)
   └── atlas_export.py  →  haalt FRED-data, berekent scores
        └── public/atlas_data.json
             └── React-dashboard (Vite)  →  GitHub Pages
```

**Waarom voorberekenen en niet live fetchen:**
1. Je FRED-key mag nooit in de browser — die is dan voor iedereen leesbaar.
2. De FRED API blokkeert browser-requests sowieso (CORS).
3. De eenzijdige HP-filter is zwaar; die wil je niet per pageview draaien.
4. De data verandert maandelijks. Live fetchen levert niets op.

---

## Eenmalige opzet

### 1. Repo aanmaken

Maak een lege repo op GitHub (bijv. `atlas`) en zet deze bestanden erin:

```
atlas/
├── atlas.py                    # de motor: indicatoren, transformaties, scores
├── atlas_backtest.py           # validatie tegen 1987 / 2000 / 2007 / 2022
├── atlas_export.py             # schrijft atlas_data.json
├── requirements.txt
├── package.json
├── vite.config.js
├── index.html
├── src/
│   ├── main.jsx
│   └── Atlas.jsx               # het dashboard
└── .github/workflows/atlas.yml # de automatisering
```

### 2. API-key als secret

GitHub → je repo → **Settings → Secrets and variables → Actions → New repository secret**

- Naam: `FRED_API_KEY`
- Waarde: je key

Zo staat hij nergens in de code. Zet hem ook nooit in een commit.

### 3. Pages aanzetten

**Settings → Pages → Source: GitHub Actions**

### 4. Base path

In `vite.config.js` moet `base` de naam van je repo zijn:

```js
export default { base: "/atlas/" }   // bij github.com/jouwnaam/atlas
```

Bij een eigen domein of een `jouwnaam.github.io`-repo: `base: "/"`.

### 5. Starten

Push naar `main`, of ga naar de **Actions**-tab en draai de workflow handmatig
(*Run workflow*). Na ~2 minuten staat het dashboard op
`https://jouwnaam.github.io/atlas/`.

---

## Lokaal draaien

```bash
pip install -r requirements.txt
export FRED_API_KEY=jouw_key          # Windows: set FRED_API_KEY=...

python atlas_export.py --fetch -o public/atlas_data.json   # data ophalen
python atlas_backtest.py                                   # validatie

npm install
npm run dev                            # http://localhost:5173
```

Zonder `atlas_data.json` draait het dashboard op **voorbeelddata**, met een
duidelijke waarschuwingsbalk. Dat is expres: een dashboard dat verzonnen cijfers
als echt presenteert is erger dan geen dashboard.

---

## Bestanden

| Bestand | Doet |
|---|---|
| `atlas.py` | Indicatordefinities, point-in-time transformaties, pijlerwegingen, scoreberekening |
| `atlas_backtest.py` | AUC, hit rate, lead time en false positives tegen historische pieken |
| `atlas_export.py` | Draait de pipeline en schrijft `atlas_data.json` |
| `src/Atlas.jsx` | Het dashboard |

## Onderhoud

- **Nieuwe indicator toevoegen:** één regel in `INDICATORS` in `atlas.py`. De rest
  (backtest, export, dashboard) pikt hem automatisch op.
- **Wegingen aanpassen:** `PILLARS` in `atlas.py`. Draai daarna de backtest om te
  zien wat het met de AUC doet.
- **Een FRED-serie is hernoemd:** de `--fetch` toont per indicator `MISLUKT`.
  Zoek het nieuwe ID op fred.stlouisfed.org en pas het aan.

## De waarschuwing die erbij hoort

ATLAS is gekalibreerd op ~5 events. Dat is te weinig voor statistische zekerheid,
hoe geavanceerd het model ook oogt. Behandel de score als een **thermometer, geen
kristallen bol**: hij zegt hoe fragiel het systeem is, niet wanneer het breekt.
Echte validatie vraagt om het landenpanel (Jordà-Schularick-Taylor, 18 landen,
1870–heden) — dat is de volgende stap.
