/*  ATLAS — dashboard
 *
 *  VORMGEVING: barografpapier. Een barograaf is een barometer die zichzelf
 *  schrijft: een pen op een langzaam draaiende trommel, die dagenlang de
 *  luchtdruk registreert. Je leest er geen moment in af, maar een BEWEGING.
 *  Dat is precies wat ATLAS is - geen alarm dat afgaat, maar een naald die
 *  al jaren dezelfde kant op kruipt. Vandaar het bleke rasterpapier, de rode
 *  inktlijn en de haarlijnen op de crisisjaren.
 *
 *  DRIE METERS, DRIE STATUSSEN. Dat onderscheid is het belangrijkste dat dit
 *  dashboard doet:
 *    KREDIET  - gevalideerd op 61 bankencrises in 18 landen (AUC 0,68)
 *    ZEEPBEL  - NIET gevalideerd (maar 4 crashes; elke AUC is ruis)
 *    EUFORIE  - beschrijvend, voorspelt niets, meet een toestand
 */

import { useEffect, useState } from "react";

const C = {
  paper: "#E7EDE4",
  paperDeep: "#DBE3D7",
  grid: "#C2CFBD",
  gridFine: "#D3DDCF",
  ink: "#1B2A21",
  inkSoft: "#5A6B60",
  trace: "#A8382C",
  amber: "#B07420",
  rule: "#9FB09A",
};

const FONTS = `
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@400;600;700&family=IBM+Plex+Serif:ital,wght@0,400;1,400&display=swap');
* { box-sizing: border-box; }
body { margin: 0; }
.atlas { background: ${C.paper}; color: ${C.ink};
  font-family: 'IBM Plex Sans Condensed', system-ui, sans-serif;
  min-height: 100vh; padding: 0 0 6rem; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 1.5rem; }
.bar { position: sticky; top: 0; z-index: 50; background: ${C.paper};
  border-bottom: 1px solid ${C.rule}; }
.bar-in { max-width: 1080px; margin: 0 auto; padding: .7rem 1.5rem;
  display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
.wordmark { font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 700;
  letter-spacing: .22em; text-transform: uppercase; font-size: .95rem; }
.eyebrow { font-family: 'IBM Plex Mono', monospace; font-size: .7rem;
  letter-spacing: .18em; text-transform: uppercase; color: ${C.inkSoft}; }
.mono { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }
.serif { font-family: 'IBM Plex Serif', Georgia, serif; }
h1 { font-size: clamp(2.4rem, 7vw, 4.2rem); font-weight: 700; letter-spacing: .04em;
  text-transform: uppercase; margin: .2rem 0 0; line-height: .95; }
h2 { font-size: 1rem; font-weight: 700; letter-spacing: .16em; text-transform: uppercase;
  margin: 0 0 1.2rem; padding-bottom: .5rem; border-bottom: 1px solid ${C.rule}; }
.card { background: ${C.paperDeep}; border: 1px solid ${C.rule}; padding: 1.4rem 1.5rem 1.6rem; }
.readout { font-family: 'IBM Plex Mono', monospace; font-size: 3.4rem; font-weight: 600;
  line-height: 1; font-variant-numeric: tabular-nums; }
.badge { font-family: 'IBM Plex Mono', monospace; font-size: .62rem; letter-spacing: .1em;
  text-transform: uppercase; padding: .22rem .5rem; border: 1px solid currentColor; }
table { width: 100%; border-collapse: collapse; font-family: 'IBM Plex Mono', monospace;
  font-size: .82rem; font-variant-numeric: tabular-nums; }
th { text-align: right; font-weight: 500; color: ${C.inkSoft}; font-size: .66rem;
  letter-spacing: .1em; text-transform: uppercase; padding: .4rem .5rem;
  border-bottom: 1px solid ${C.rule}; }
th:first-child, td:first-child { text-align: left; }
td { padding: .42rem .5rem; text-align: right; border-bottom: 1px solid ${C.gridFine}; }
tr.hi td { background: rgba(168,56,44,.09); font-weight: 600; }
tr.base td { color: ${C.inkSoft}; font-style: italic; }
a { color: ${C.trace}; }
.grid3 { display: grid; gap: 1rem; grid-template-columns: repeat(3, 1fr); }
.grid2 { display: grid; gap: 2rem; grid-template-columns: 1fr 1fr; }
@media (max-width: 860px) { .grid3, .grid2 { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: no-preference) {
  .pen { animation: draw 2.4s ease-out forwards; }
  @keyframes draw { from { stroke-dashoffset: var(--len); } to { stroke-dashoffset: 0; } }
}
`;

/* ---------------------------------------------------------------- *
 *  DE SIGNATUUR: de schrijvende barograaf.
 *  Vijftig jaar ATLAS-KREDIET als één doorlopende inktlijn op rasterpapier.
 *  De crisisjaren staan er als haarlijnen in - niet als versiering, maar
 *  omdat je alleen zo kunt zien of de naald ervoor omhoog kroop.
 * ---------------------------------------------------------------- */
function Barograaf({ history, peaks }) {
  const W = 1040, H = 260, PL = 44, PR = 16, PT = 14, PB = 26;
  const pts = history.filter((d) => d.atlas != null);
  if (!pts.length) return null;

  const t0 = new Date(pts[0].date).getTime();
  const t1 = new Date(pts[pts.length - 1].date).getTime();
  const x = (d) => PL + ((new Date(d).getTime() - t0) / (t1 - t0)) * (W - PL - PR);
  const y = (v) => PT + (1 - v / 100) * (H - PT - PB);

  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.atlas).toFixed(1)}`).join("");
  const last = pts[pts.length - 1];
  const jaren = [];
  for (let j = 1980; j <= new Date(t1).getFullYear(); j += 10) jaren.push(j);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
         aria-label="ATLAS-KREDIET van 1976 tot nu, met de crisisjaren gemarkeerd"
         style={{ display: "block", background: C.paper, border: `1px solid ${C.rule}` }}>
      {/* rasterpapier */}
      {[0, 20, 40, 60, 80, 100].map((v) => (
        <g key={v}>
          <line x1={PL} x2={W - PR} y1={y(v)} y2={y(v)}
                stroke={v === 60 || v === 80 ? C.grid : C.gridFine}
                strokeWidth={v === 60 || v === 80 ? 1 : 0.6}
                strokeDasharray={v === 60 || v === 80 ? "3 3" : ""} />
          <text x={PL - 8} y={y(v) + 3.5} textAnchor="end" fontSize="9"
                fontFamily="IBM Plex Mono, monospace" fill={C.inkSoft}>{v}</text>
        </g>
      ))}
      {jaren.map((j) => (
        <g key={j}>
          <line x1={x(`${j}-01-01`)} x2={x(`${j}-01-01`)} y1={PT} y2={H - PB}
                stroke={C.gridFine} strokeWidth="0.6" />
          <text x={x(`${j}-01-01`)} y={H - PB + 14} textAnchor="middle" fontSize="9"
                fontFamily="IBM Plex Mono, monospace" fill={C.inkSoft}>{j}</text>
        </g>
      ))}

      {/* de crises: haarlijnen door het papier */}
      {peaks.filter((p) => new Date(p.date + "-01") >= new Date(pts[0].date)).map((p) => (
        <g key={p.date}>
          <line x1={x(p.date + "-01")} x2={x(p.date + "-01")} y1={PT} y2={H - PB}
                stroke={p.exogenous ? C.inkSoft : C.ink} strokeWidth="0.8"
                strokeDasharray={p.exogenous ? "2 4" : ""} opacity="0.55" />
          <text x={x(p.date + "-01") + 3} y={PT + 10} fontSize="8.5"
                fontFamily="IBM Plex Mono, monospace" fill={C.ink} opacity="0.75">
            {p.date.slice(0, 4)}
          </text>
        </g>
      ))}

      {/* de inktlijn */}
      <path d={path} fill="none" stroke={C.trace} strokeWidth="1.6"
            strokeLinejoin="round" className="pen"
            style={{ strokeDasharray: 6000, "--len": 6000 }} />

      {/* de pen, op de stand van vandaag */}
      <circle cx={x(last.date)} cy={y(last.atlas)} r="3.6" fill={C.trace} />
      <circle cx={x(last.date)} cy={y(last.atlas)} r="7" fill="none"
              stroke={C.trace} strokeWidth="0.8" opacity="0.5" />
    </svg>
  );
}

/* Waar staat dit cijfer, vergeleken met alles wat eraan voorafging? */
function Schaal({ waarde, merken = [] }) {
  return (
    <svg viewBox="0 0 300 34" width="100%" style={{ display: "block", marginTop: ".9rem" }}>
      <line x1="2" x2="298" y1="20" y2="20" stroke={C.rule} strokeWidth="1" />
      {[0, 25, 50, 75, 100].map((v) => (
        <g key={v}>
          <line x1={2 + v * 2.96} x2={2 + v * 2.96} y1="16" y2="24" stroke={C.rule} strokeWidth="1" />
          <text x={2 + v * 2.96} y="33" textAnchor="middle" fontSize="7"
                fontFamily="IBM Plex Mono, monospace" fill={C.inkSoft}>{v}</text>
        </g>
      ))}
      {merken.map((m) => (
        <g key={m.label}>
          <line x1={2 + m.v * 2.96} x2={2 + m.v * 2.96} y1="10" y2="20"
                stroke={C.ink} strokeWidth="0.8" opacity="0.6" />
          <text x={2 + m.v * 2.96} y="7" textAnchor="middle" fontSize="7"
                fontFamily="IBM Plex Mono, monospace" fill={C.ink} opacity="0.8">{m.label}</text>
        </g>
      ))}
      <polygon points={`${2 + waarde * 2.96},13 ${2 + waarde * 2.96 - 5},22 ${2 + waarde * 2.96 + 5},22`}
               fill={C.trace} />
    </svg>
  );
}

function Meter({ titel, waarde, status, statusKleur, uitleg, componenten, merken, per }) {
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
        <div className="eyebrow">{titel}</div>
        <span className="badge" style={{ color: statusKleur }}>{status}</span>
      </div>
      <div className="readout" style={{ marginTop: ".7rem", color: C.trace }}>
        {waarde ?? "—"}
        <span style={{ fontSize: "1rem", color: C.inkSoft, marginLeft: ".4rem" }}>/100</span>
      </div>
      <div className="mono" style={{ fontSize: ".68rem", color: C.inkSoft, marginTop: ".2rem" }}>
        stand per {per}
      </div>
      <Schaal waarde={waarde ?? 0} merken={merken} />
      <p className="serif" style={{ fontSize: ".84rem", lineHeight: 1.5, color: C.inkSoft,
                                    margin: "1rem 0 .8rem" }}>{uitleg}</p>
      {componenten?.length > 0 && (
        <table>
          <tbody>
            {componenten.map((c) => (
              <tr key={c.naam}>
                <td style={{ fontSize: ".74rem" }}>{c.naam}</td>
                <td style={{ color: C.inkSoft, fontSize: ".7rem" }}>
                  {c.weging ? `${Math.round(c.weging * 100)}%` : ""}
                </td>
                <td style={{ fontWeight: 600, color: c.stand == null ? C.inkSoft : C.ink }}>
                  {c.stand == null ? "—" : Math.round(c.stand)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function Atlas() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}atlas_data.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setD)
      .catch((e) => setErr(e.message));
  }, []);

  if (err) return (
    <div className="atlas"><style>{FONTS}</style><div className="wrap" style={{ paddingTop: "4rem" }}>
      <div className="eyebrow">Geen data</div>
      <p className="serif">atlas_data.json is niet geladen ({err}). Draai{" "}
        <code className="mono">python3 atlas_export.py --fetch -o public/atlas_data.json</code>.</p>
    </div></div>
  );
  if (!d) return (
    <div className="atlas"><style>{FONTS}</style>
      <div className="wrap" style={{ paddingTop: "4rem" }}><div className="eyebrow">Laden…</div></div>
    </div>
  );

  const jst = d.jst ?? {};
  const zb = d.zeepbel?.error ? null : d.zeepbel;
  const ef = d.euforie?.error ? null : d.euforie;
  const S = { marginTop: "4rem" };

  return (
    <div className="atlas">
      <style>{FONTS}</style>

      {/* ---------------- blijvende balk ---------------- */}
      <div className="bar">
        <div className="bar-in">
          <span className="wordmark">Atlas</span>
          <span className="mono" style={{ fontSize: ".78rem", color: C.inkSoft }}>
            <strong style={{ color: C.trace, fontSize: "1rem" }}>{d.current?.score}</strong>
            <span style={{ margin: "0 .4rem" }}>·</span>
            <span style={{ textTransform: "uppercase", letterSpacing: ".1em" }}>
              {d.current?.regime}
            </span>
          </span>
        </div>
      </div>

      {/* ---------------- masthead ---------------- */}
      <header className="wrap" style={{ paddingTop: "3rem", paddingBottom: "2rem" }}>
        <div className="eyebrow">Advanced Tracking of Long-term Asset Stability</div>
        <h1>Atlas</h1>
        <p className="serif" style={{ maxWidth: "54ch", fontSize: "1.02rem", lineHeight: 1.6,
                                      marginTop: "1.1rem", color: C.inkSoft }}>
          Drie meters voor de lange financiële cyclus. Ze meten hoeveel spanning er is opgebouwd,
          niet wanneer die zich ontlaadt. Een indicatie, geen zekerheid.
        </p>
      </header>

      {/* ---------------- signatuur: de barograaf ---------------- */}
      <section className="wrap">
        <Barograaf history={d.history} peaks={d.peaks} />
        <div className="mono" style={{ fontSize: ".68rem", color: C.inkSoft, marginTop: ".5rem",
                                       display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: ".5rem" }}>
          <span>ATLAS-KREDIET, maandelijks — verticale lijnen zijn crisistoppen (gestippeld = exogeen)</span>
          <span>
            stand per {d.current?.date} · dekking{" "}
            {Math.round((d.current?.coverage ?? 0) * 100)}%
            {d.current?.maanden_achterstand > 0 &&
              ` · kwartaaldata loopt ${d.current.maanden_achterstand} mnd achter`}
          </span>
        </div>
      </section>

      {/* ---------------- euforie door de tijd ---------------- */}
      {ef?.traject && (
        <section className="wrap" style={S}>
          <h2>Hoe heet werd het, en wanneer?</h2>
          <svg viewBox="0 0 1040 200" width="100%"
               style={{ border: `1px solid ${C.rule}`, background: C.paper, display: "block" }}>
            {[25, 50, 75, 100].map((v) => (
              <line key={v} x1="30" x2="1030" y1={180 - v * 1.5} y2={180 - v * 1.5}
                    stroke={C.gridFine} strokeWidth="0.6" />
            ))}
            {ef.traject.map((t, i) => {
              const bw = 1000 / ef.traject.length;
              const x = 30 + i * bw;
              const h = t.score * 1.5;
              const nu = i === ef.traject.length - 1;
              return (
                <g key={t.jaar}>
                  <rect x={x + 1} y={180 - h} width={bw - 2} height={h}
                        fill={nu ? C.trace : t.score >= 90 ? C.amber : C.inkSoft}
                        opacity={nu ? 1 : t.score >= 90 ? 0.85 : 0.45} />
                  {t.jaar % 10 === 0 && (
                    <text x={x + bw / 2} y="195" textAnchor="middle" fontSize="9"
                          fontFamily="IBM Plex Mono, monospace" fill={C.inkSoft}>{t.jaar}</text>
                  )}
                </g>
              );
            })}
          </svg>
          <p className="serif" style={{ fontSize: ".9rem", lineHeight: 1.65, maxWidth: "64ch" }}>
            Elke staaf is de hoogste stand in dat jaar. Let op hoe lang een hete markt heet kan
            blijven: de speculatieve fase van de jaren negentig begon rond 1995 en duurde vijf jaar.
            Een hoge stand zegt waar je staat, niet wat er morgen gebeurt.
          </p>
        </section>
      )}

      {/* ---------------- de drie meters ---------------- */}
      <section className="wrap" style={S}>
        <h2>De drie meters</h2>
        <div className="grid3">
          <Meter
            titel="Atlas-krediet"
            waarde={d.current?.score}
            per={d.current?.date}
            status={`gevalideerd · auc ${String(jst.auc_streng ?? "").replace(".", ",")}`}
            statusKleur={C.ink}
            uitleg="Bouwt de kredietcyclus op uit schuld, waardering, rente, gedrag en geopolitiek. Als enige getoetst buiten de eigen data: op 61 bankencrises in 18 landen, zonder dat er één parameter op is afgesteld."
            componenten={d.pillars?.map((p) => ({ naam: p.label, stand: p.score, weging: p.weight }))}
            merken={[{ v: 60, label: "verhoogd" }, { v: 80, label: "kritiek" }]}
          />
          <Meter
            titel="Atlas-zeepbel"
            waarde={zb?.combinatie}
            per={zb?.datum}
            status="niet gevalideerd"
            statusKleur={C.amber}
            uitleg="Dure markt én versnellende koers. Sinds 1960 zijn er maar vier beurscrashes geweest — te weinig om dit hard te toetsen. Lees het als een vermoeden."
            componenten={zb ? [
              { naam: "Waardering", stand: zb.waardering },
              { naam: "Melt-up (versnelling)", stand: zb.meltup },
            ] : []}
            merken={[{ v: 80, label: "hoog" }]}
          />
          <Meter
            titel="Atlas-euforie"
            waarde={ef?.score}
            per={ef?.datum}
            status="beschrijvend"
            statusKleur={C.inkSoft}
            uitleg="Hoeveel hefboom, hoeveel particuliere inleg, hoe duur, hoe snel — afgezet tegen de eigen geschiedenis, gecorrigeerd voor de structurele groei van hefboom. Meet de toestand, niet het moment."
            componenten={ef?.componenten?.map((c) => ({ naam: c.naam, stand: c.stand, weging: c.weging }))}
            merken={[{ v: 90, label: "extreem" }]}
          />
        </div>
      </section>

      {/* ---------------- rendement: de vraag die wél te beantwoorden is ---------------- */}
      {zb?.rendement?.j10 && (
        <section className="wrap" style={S}>
          <h2>Wat leverde deze waardering historisch op?</h2>
          <div className="grid2">
            <div>
              <p className="serif" style={{ fontSize: ".92rem", lineHeight: 1.65, marginTop: 0 }}>
                <em>Wanneer knapt het?</em> is onbeantwoordbaar — vier crashes is geen statistiek.
                <em> Wat krijg ik hier nog voor betaald?</em> is dat wél. Het verband tussen
                waardering en het rendement daarna is een van de best gerepliceerde bevindingen in
                de financiële economie, en daarvoor bestaan honderdvijftig jaar aan waarnemingen.
              </p>
              <p className="serif" style={{ fontSize: ".92rem", lineHeight: 1.65 }}>
                Reëel totaalrendement, inclusief herbelegd dividend, na inflatie, op jaarbasis.
                Bron: Shiller, 1871–heden. De vensters overlappen, dus lees de richting, niet de
                komma achter het cijfer.
              </p>
            </div>
            <div>
              <table>
                <thead>
                  <tr>
                    <th>Waardering</th><th>mediaan</th><th>slechtste</th>
                    <th>beste</th><th>kans &lt;0%</th>
                  </tr>
                </thead>
                <tbody>
                  {zb.rendement.j10.map((r) => {
                    const [lo, hi] = r.band.split("-").map(Number);
                    const hier = zb.waardering >= lo && zb.waardering < (hi === 100 ? 101 : hi);
                    return (
                      <tr key={r.band} className={hier ? "hi" : ""}>
                        <td>{r.band}{hier ? "  ← nu" : ""}</td>
                        <td>{r.mediaan > 0 ? "+" : ""}{String(r.mediaan).replace(".", ",")}%</td>
                        <td>{String(r.slechtste).replace(".", ",")}%</td>
                        <td>+{String(r.beste).replace(".", ",")}%</td>
                        <td>{Math.round(r.kans_verlies * 100)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="mono" style={{ fontSize: ".7rem", marginTop: ".7rem",
                                             paddingTop: ".6rem", borderTop: `1px solid ${C.rule}`,
                                             color: C.trace, fontWeight: 600 }}>
                nu: waardering {zb.waardering} → zie de gemarkeerde rij
              </div>
              <div className="mono" style={{ fontSize: ".66rem", color: C.inkSoft, marginTop: ".3rem" }}>
                over de tien jaar ná het instapmoment
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ---------------- de drempeltabel: het echte antwoord ---------------- */}
      {jst.drempels && (
        <section className="wrap" style={S}>
          <h2>Wat volgt er op deze stand?</h2>
          <div className="grid2">
            <div>
              <p className="serif" style={{ fontSize: ".92rem", lineHeight: 1.65, marginTop: 0 }}>
                Dit is de tabel waar het om draait. Hij komt uit de{" "}
                <strong>Jordà-Schularick-Taylor-database</strong>: {jst.landen} landen,{" "}
                {jst.landjaren?.toLocaleString("nl-NL")} landjaren, <strong>{jst.crises} bankencrises</strong>.
                Geen enkele parameter van ATLAS is op deze data afgesteld — daarom telt dit cijfer,
                en niet de {String(jst.auc_vs_insample ?? "").replace(".", ",")} die het model op
                Amerikaanse data haalt.
              </p>
              {(() => {
                const nu = jst.drempels.find((r) => {
                  const [lo, hi] = r.band.split("-").map(Number);
                  return d.current?.score >= lo && d.current?.score < (hi === 100 ? 101 : hi);
                });
                if (!nu) return null;
                return (
                  <div style={{ background: C.paperDeep, border: `1px solid ${C.trace}`,
                                padding: "1rem 1.1rem", marginTop: "1.2rem" }}>
                    <div className="eyebrow" style={{ color: C.trace }}>Waar staan we nu</div>
                    <p className="serif" style={{ fontSize: ".95rem", lineHeight: 1.6, margin: ".5rem 0 0" }}>
                      ATLAS-KREDIET staat op <strong>{d.current.score}</strong> — dat is band{" "}
                      <strong>{nu.band}</strong>. In die band volgde er in{" "}
                      <strong>{Math.round(nu.j5 * 100)}%</strong> van de gevallen een bankencrisis
                      binnen vijf jaar, tegen {Math.round((jst.alle_jaren?.j5 ?? 0) * 100)}% over
                      alle jaren samen.
                    </p>
                  </div>
                );
              })()}
            </div>
            <div>
              <table>
                <thead>
                  <tr>
                    <th>Meterstand</th><th>&lt;3 jaar</th><th>&lt;5 jaar</th>
                    <th>&lt;10 jaar</th><th>landjaren</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="base">
                    <td>alle jaren</td>
                    <td>{Math.round(jst.alle_jaren.j3 * 100)}%</td>
                    <td>{Math.round(jst.alle_jaren.j5 * 100)}%</td>
                    <td>{Math.round(jst.alle_jaren.j10 * 100)}%</td>
                    <td>{jst.alle_jaren.jaren}</td>
                  </tr>
                  {jst.drempels.map((r) => {
                    const [lo, hi] = r.band.split("-").map(Number);
                    const hier = d.current?.score >= lo && d.current?.score < (hi === 100 ? 101 : hi);
                    return (
                      <tr key={r.band} className={hier ? "hi" : ""}>
                        <td>{r.band}{hier ? "  ← nu" : ""}</td>
                        <td>{Math.round(r.j3 * 100)}%</td>
                        <td>{Math.round(r.j5 * 100)}%</td>
                        <td>{Math.round(r.j10 * 100)}%</td>
                        <td>{r.jaren}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* ---------------- wat zit er in elke pijler ---------------- */}
      <section className="wrap" style={S}>
        <h2>Wat er in elke pijler zit</h2>
        <p className="serif" style={{ fontSize: ".92rem", lineHeight: 1.65, maxWidth: "64ch",
                                      marginTop: 0 }}>
          ATLAS-KREDIET is opgebouwd uit vijf pijlers. Elke indicator wordt omgezet naar een schaal
          van 0 tot 100 door hem te vergelijken met zijn eigen verleden — met alleen de data die op
          dat moment beschikbaar was. Een <strong>richting van −1</strong> betekent dat een lage
          waarde juist risico signaleert (een omgekeerde rentecurve, bijvoorbeeld).
        </p>

        {d.pillars?.map((p) => {
          const leden = (d.indicators ?? []).filter((i) => i.pillar === p.label);
          if (!leden.length) return null;
          return (
            <div key={p.key} style={{ marginTop: "2rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between",
                            alignItems: "baseline", borderBottom: `1px solid ${C.rule}`,
                            paddingBottom: ".4rem", marginBottom: ".2rem" }}>
                <div className="eyebrow" style={{ color: C.ink }}>
                  {p.label} · {Math.round(p.weight * 100)}% van de score
                </div>
                <div className="mono" style={{ fontSize: ".9rem", fontWeight: 600,
                                               color: p.score == null ? C.inkSoft : C.trace }}>
                  {p.score == null ? "geen data" : p.score}
                </div>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Indicator</th><th style={{ textAlign: "left" }}>Bron</th>
                    <th>richting</th><th>per</th><th>stand</th>
                  </tr>
                </thead>
                <tbody>
                  {leden.map((i) => (
                    <tr key={i.name}>
                      <td style={{ fontSize: ".8rem" }}>{i.name}</td>
                      <td style={{ textAlign: "left", fontSize: ".7rem", color: C.inkSoft }}>
                        {i.series_id ?? "—"}
                      </td>
                      <td style={{ color: i.direction < 0 ? C.amber : C.inkSoft }}>
                        {i.direction > 0 ? "+1" : i.direction < 0 ? "−1" : "—"}
                      </td>
                      <td style={{ color: C.inkSoft, fontSize: ".72rem" }}>
                        {i.per ? i.per.slice(0, 7) : "—"}
                      </td>
                      <td style={{ fontWeight: 600 }}>
                        {i.score == null
                          ? <span style={{ color: C.inkSoft, fontWeight: 400 }}>
                              {i.error ?? "—"}
                            </span>
                          : Math.round(i.score)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </section>

      {/* ---------------- waar de cijfers vandaan komen ---------------- */}
      <section className="wrap" style={S}>
        <h2>Waar dit vandaan komt</h2>
        <div className="grid2">
          <div>
            {d.bronnen?.map((b) => (
              <div key={b.naam} style={{ marginBottom: "1.1rem" }}>
                <div className="mono" style={{ fontSize: ".78rem", fontWeight: 600 }}>
                  <a href={b.url} target="_blank" rel="noreferrer">{b.naam}</a>
                </div>
                <div className="serif" style={{ fontSize: ".85rem", color: C.inkSoft, lineHeight: 1.5 }}>
                  {b.wat}
                </div>
              </div>
            ))}
          </div>
          <div>
            <p className="serif" style={{ fontSize: ".9rem", lineHeight: 1.65, marginTop: 0 }}>
              Alle indicatoren worden <strong>point-in-time</strong> geijkt: de stand van 1995 wordt
              beoordeeld met de gegevens die in 1995 beschikbaar waren, niet met de kennis van nu.
              Zonder die discipline ziet elk model er achteraf briljant uit.
            </p>
            <p className="serif" style={{ fontSize: ".9rem", lineHeight: 1.65 }}>
              Wat ATLAS <em>niet</em> kan: het moment aanwijzen. Aandelenzeepbellen knappen op een
              eigen ritme dat dit model niet vangt (AUC 0,47 op 89 zeepbellen — dat is een muntje
              opgooien). Japan stond in 1987 op zijn hoogste stand; de bankencrisis kwam in 1997.
            </p>
            <div className="mono" style={{ fontSize: ".72rem", color: C.inkSoft, marginTop: "1.4rem",
                                           paddingTop: ".8rem", borderTop: `1px solid ${C.rule}` }}>
              in-sample VS: {String(jst.auc_vs_insample ?? "").replace(".", ",")} ·
              out-of-sample panel: {String(jst.auc_streng ?? "").replace(".", ",")} ·
              het tweede getal is het echte
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
