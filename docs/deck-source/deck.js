const pptxgen = require("pptxgenjs");
const React = require("react");
const RDS = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require(process.env.SK + "/scripts/apply_theme.js");

const OUT = process.argv[2];
const THEME = {
  name: "DisputeIQ Ledger",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "16232B", lt1: "FFFFFF", dk2: "0F3B47", lt2: "EEF3F4",
    accent1: "0F766E", accent2: "B45309", accent3: "B91C1C", accent4: "1D4ED8",
    accent5: "64748B", accent6: "15803D", hlink: "0F766E", folHlink: "0F3B47",
  },
};
const HEX = THEME.colors;

async function icon(Comp, color) {
  const svg = RDS.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: 256 }));
  const buf = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9"; // 10 x 5.625
  pres.title = "DisputeIQ - Zeta Innovate 2026";
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  pres.defineSlideMaster({
    title: "Title Dark",
    background: { color: HEX.dk2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.55, w: 8.8, h: 1.1, fontSize: 44, bold: true, color: C.background1, fontFace: THEME.headFontFace, valign: "bottom", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 2.75, w: 8.8, h: 1.2, fontSize: 18, color: C.background2, valign: "top", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "Content",
    background: { color: HEX.lt1 },
    margin: [0.5, 0.5, 0.5, 0.5],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 9.0, h: 0.7, fontSize: 30, bold: true, color: C.text2, fontFace: THEME.headFontFace, valign: "middle", margin: 0 }, text: "" } },
      { text: { text: "DisputeIQ · Zeta Innovate 2026", options: { x: 0.5, y: 5.25, w: 5, h: 0.25, fontSize: 9, color: C.accent5, margin: 0 } } },
    ],
    slideNumber: { x: 9.1, y: 5.25, w: 0.4, h: 0.25, fontSize: 9, color: "64748B" },
  });

  const card = (s, x, y, w, h, fill, name) =>
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: fill }, objectName: name });
  const txt = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, fontSize: 14, color: C.text1, valign: "top", ...o });
  const circleIcon = async (s, Comp, x, y, d, bg) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg }, line: { color: bg } });
    s.addImage({ data: await icon(Comp, "FFFFFF"), x: x + d * 0.22, y: y + d * 0.22, w: d * 0.56, h: d * 0.56 });
  };

  // 1 Title -------------------------------------------------------------------------------
  pres.addSection({ title: "Opening" });
  let s = pres.addSlide({ masterName: "Title Dark", sectionTitle: "Opening" });
  s.addText("DisputeIQ", { placeholder: "title" });
  s.addText("An AI dispute-resolution agent for card issuers that recommends, explains and routes, with humans deciding anything risky", { placeholder: "body" });
  await circleIcon(s, fa.FaShieldAlt, 0.6, 0.6, 0.75, HEX.accent1);
  txt(s, "Zeta Innovate 2026", { x: 0.6, y: 4.7, w: 5, h: 0.35, fontSize: 14, color: C.background2 });
  s.addNotes("One sentence: DisputeIQ reads a card dispute, gathers evidence from the bank's own records, applies policy in code and either resolves a low-risk case or hands a well-prepared case to an analyst.");

  // 2 Problem -----------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Opening" });
  s.addText("Card disputes are slow and easy to game", { placeholder: "title" });
  const probs = [
    [fa.FaClock, "Manual work", "Analysts read free text, look up transactions, check windows and draft letters for every case."],
    [fa.FaCalendarTimes, "Hard deadlines", "Network dispute windows expire; a missed window means the issuer absorbs the loss."],
    [fa.FaUserSecret, "Friendly fraud", "\"I didn't make this\" on an OTP-authenticated payment needs judgement, not automation."],
  ];
  for (let i = 0; i < 3; i++) {
    const x = 0.5 + i * 3.05;
    card(s, x, 1.3, 2.85, 3.5, HEX.lt2, `problem-${i}`);
    await circleIcon(s, probs[i][0], x + 0.3, 1.55, 0.7, HEX.accent2);
    txt(s, probs[i][1], { x: x + 0.3, y: 2.45, w: 2.3, h: 0.45, fontSize: 18, bold: true, color: C.text2, fontFace: THEME.headFontFace });
    txt(s, probs[i][2], { x: x + 0.3, y: 2.95, w: 2.3, h: 1.7, fontSize: 14 });
  }
  s.addNotes("Keep the problem qualitative unless you have opened the RBI primary source. If you cite a figure, give the year and source on the slide; RBI card/internet fraud figures were revised between releases.");

  // 3 Solution ----------------------------------------------------------------------------
  pres.addSection({ title: "Solution" });
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Solution" });
  s.addText("Same investigation, done as a traceable pipeline", { placeholder: "title" });
  card(s, 0.5, 1.25, 4.3, 3.6, HEX.lt2, "manual");
  card(s, 5.2, 1.25, 4.3, 3.6, HEX.accent1, "diq");
  txt(s, "Manual today", { x: 0.8, y: 1.45, w: 3.7, h: 0.45, fontSize: 20, bold: true, color: C.text2, fontFace: THEME.headFontFace });
  txt(s, [
    { text: "Read the complaint and guess the claim type", options: { bullet: true, breakLine: true } },
    { text: "Search for the transaction by hand", options: { bullet: true, breakLine: true } },
    { text: "Check deadlines and evidence from memory", options: { bullet: true, breakLine: true } },
    { text: "Write the letter and the filing", options: { bullet: true } },
  ], { x: 0.8, y: 2.0, w: 3.8, h: 2.6, paraSpaceAfter: 8 });
  txt(s, "With DisputeIQ", { x: 5.5, y: 1.45, w: 3.7, h: 0.45, fontSize: 20, bold: true, color: C.background1, fontFace: THEME.headFontFace });
  txt(s, [
    { text: "PII masked, facts extracted, claim classified", options: { bullet: true, breakLine: true } },
    { text: "Transaction matched and evidence checked in code", options: { bullet: true, breakLine: true } },
    { text: "Policy and deadline computed deterministically", options: { bullet: true, breakLine: true } },
    { text: "Low-risk refunds auto-resolve; the rest go to an analyst with drafts", options: { bullet: true } },
  ], { x: 5.5, y: 2.0, w: 3.8, h: 2.6, paraSpaceAfter: 8, color: C.background1 });
  s.addNotes("No time-saving number here: we have not measured one. Say 'designed to remove the lookup and drafting work'.");

  // 4 Architecture ------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Solution" });
  s.addText("Architecture as deployed", { placeholder: "title" });
  const box = async (x, y, w, h, title, sub, Comp, fill, fg) => {
    card(s, x, y, w, h, fill, title);
    await circleIcon(s, Comp, x + 0.2, y + (h - 0.55) / 2, 0.55, HEX.dk2);
    txt(s, title, { x: x + 0.9, y: y + 0.15, w: w - 1.05, h: 0.4, fontSize: 16, bold: true, color: fg });
    txt(s, sub, { x: x + 0.9, y: y + 0.55, w: w - 1.05, h: h - 0.65, fontSize: 12, color: fg });
  };
  await box(0.5, 1.4, 2.7, 1.5, "React + Vite", "Vercel. Reviewer sign-in, queue, case page, metrics", fa.FaDesktop, HEX.lt2, C.text1);
  await box(3.65, 1.4, 2.7, 1.5, "FastAPI agent", "Render (Docker). LangGraph pipeline, rules, audit", fa.FaCogs, HEX.accent1, C.background1);
  await box(6.8, 1.4, 2.7, 1.5, "Gemini Flash", "Masked text only. Extraction, classification, explanation, prose", fa.FaBrain, HEX.lt2, C.text1);
  await box(3.65, 3.45, 2.7, 1.6, "PostgreSQL", "Customers, transactions, disputes, evidence, decisions, audit; pgvector memory", fa.FaDatabase, HEX.lt2, C.text1);
  const arrow = (x, y, w, h) => s.addShape(pres.shapes.LINE, { x, y, w, h, line: { color: HEX.accent5, width: 2, endArrowType: "triangle" } });
  arrow(3.2, 2.15, 0.45, 0); arrow(6.35, 2.15, 0.45, 0); arrow(5.0, 2.9, 0, 0.55);
  txt(s, "Offline rules engine (mock-rules-v1) processed the seeded history; live submissions use Gemini. Every decision records which engine produced it.", { x: 6.8, y: 3.45, w: 2.7, h: 1.4, fontSize: 12, color: C.text2, italic: true });
  s.addNotes("Hosted pieces are as reported by the team; verify /health on the day.");

  // 5 Pipeline ----------------------------------------------------------------------------
  pres.addSection({ title: "How it works" });
  s = pres.addSlide({ masterName: "Content", sectionTitle: "How it works" });
  s.addText("Nine audited steps: AI reads, code decides", { placeholder: "title" });
  const steps = [
    ["Mask PII", "code"], ["Extract facts", "ai"], ["Match transaction", "code"], ["Evidence checks", "code"], ["Classify", "ai"],
    ["Eligibility & deadline", "code"], ["Recommend", "code"], ["Draft letter", "ai"], ["Route", "code"],
  ];
  steps.forEach(([t, k], i) => {
    const col = i % 5, row = Math.floor(i / 5);
    const x = 0.5 + col * 1.82, y = 1.35 + row * 1.55;
    const fill = k === "ai" ? HEX.accent4 : HEX.dk2;
    card(s, x, y, 1.65, 1.2, fill, `step-${i}`);
    txt(s, String(i + 1), { x: x + 0.15, y: y + 0.12, w: 0.5, h: 0.4, fontSize: 20, bold: true, color: C.background1, fontFace: THEME.headFontFace });
    txt(s, t, { x: x + 0.15, y: y + 0.55, w: 1.4, h: 0.55, fontSize: 13, bold: true, color: C.background1 });
  });
  card(s, 0.5 + 4 * 1.82, 1.35 + 1.55, 1.65, 1.2, HEX.lt2, "legend");
  s.addShape(pres.shapes.OVAL, { x: 7.95, y: 3.05, w: 0.22, h: 0.22, fill: { color: HEX.accent4 }, line: { color: HEX.accent4 } });
  txt(s, "LLM (Gemini)", { x: 8.25, y: 3.02, w: 1.1, h: 0.3, fontSize: 11 });
  s.addShape(pres.shapes.OVAL, { x: 7.95, y: 3.5, w: 0.22, h: 0.22, fill: { color: HEX.dk2 }, line: { color: HEX.dk2 } });
  txt(s, "Deterministic code", { x: 8.25, y: 3.47, w: 1.15, h: 0.45, fontSize: 11 });
  txt(s, "Every step writes an audit event: actor, input/output summary, model, prompt version, tokens, latency, retries.", { x: 0.5, y: 4.55, w: 9.0, h: 0.5, fontSize: 13, color: C.text2 });
  s.addNotes("The model influences extraction and the reason code. It cannot set amounts, deadlines, the recommendation or the route.");

  // 6 Classification & evidence ----------------------------------------------------------
  s = pres.addSlide({ masterName: "Content", sectionTitle: "How it works" });
  s.addText("Evidence decides; auto-resolve is narrow", { placeholder: "title" });
  s.addTable([
    [{ text: "Reason code", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }, { text: "Evidence checked in code", options: { bold: true, color: "FFFFFF", fill: { color: HEX.dk2 } } }],
    ["DUPLICATE_CHARGE", "Same card, merchant, amount within 24 h"],
    ["ATM_CASH_NOT_DISPENSED", "ATM log: cash dispensed or not"],
    ["FRAUD_NOT_AUTHORISED", "Authentication method (OTP/PIN), history"],
    ["GOODS_NOT_RECEIVED", "Cannot be verified internally: human"],
    ["+ 4 more codes", "Recurring, amount, refund, not-as-described"],
  ], { x: 0.5, y: 1.3, w: 5.4, colW: [2.3, 3.1], fontSize: 12, fontFace: THEME.bodyFontFace, color: HEX.dk1, border: { type: "solid", pt: 0.5, color: "CBD5E1" }, rowH: 0.42 });
  card(s, 6.2, 1.3, 3.3, 3.55, HEX.lt2, "rule");
  txt(s, "Auto-resolve only if all hold", { x: 6.45, y: 1.45, w: 2.9, h: 0.4, fontSize: 16, bold: true, color: C.text2, fontFace: THEME.headFontFace });
  txt(s, [
    { text: "Recommendation is REFUND", options: { bullet: true, breakLine: true } },
    { text: "Duplicate or ATM code", options: { bullet: true, breakLine: true } },
    { text: "Confidence at least 0.85", options: { bullet: true, breakLine: true } },
    { text: "Amount at most ₹10,000", options: { bullet: true, breakLine: true } },
    { text: "No injection, friendly-fraud or repeat-dispute flag", options: { bullet: true, breakLine: true } },
    { text: "No other dispute on the transaction", options: { bullet: true } },
  ], { x: 6.45, y: 1.95, w: 2.9, h: 2.8, fontSize: 13, paraSpaceAfter: 4 });
  s.addNotes("Thresholds live in reason_codes.yaml. The windows and taxonomy are illustrative, not network-certified.");

  // 7 Scenarios ---------------------------------------------------------------------------
  pres.addSection({ title: "Demo" });
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Demo" });
  s.addText("Six live scenarios, six isolated demo customers", { placeholder: "title" });
  const sc = [
    ["Meera", "Duplicate ₹2,499", "Refund; auto-resolves if confidence ≥ 0.85", HEX.accent6],
    ["Rohan", "ATM ₹5,000 not dispensed", "Refund backed by the ATM log", HEX.accent6],
    ["Kavya", "Disputed OTP payment ₹8,750", "Reject recommended, human decides", HEX.accent2],
    ["Arjun", "Duplicate ₹32,000", "Refund recommended; over limit, human", HEX.accent2],
    ["Sana", "Duplicate + prompt injection", "Injection flagged and ignored; human", HEX.accent3],
    ["Isha", "Hinglish duplicate ₹999", "Same rules as English", HEX.accent4],
  ];
  sc.forEach(([n, a, b, col], i) => {
    const x = 0.5 + (i % 3) * 3.05, y = 1.3 + Math.floor(i / 3) * 1.85;
    card(s, x, y, 2.85, 1.65, HEX.lt2, `sc-${i}`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: y + 0.22, w: 0.32, h: 0.32, fill: { color: col }, line: { color: col } });
    txt(s, n, { x: x + 0.65, y: y + 0.18, w: 2.0, h: 0.4, fontSize: 18, bold: true, color: C.text2, fontFace: THEME.headFontFace });
    txt(s, a, { x: x + 0.2, y: y + 0.65, w: 2.5, h: 0.4, fontSize: 13, bold: true });
    txt(s, b, { x: x + 0.2, y: y + 1.05, w: 2.5, h: 0.5, fontSize: 12, color: C.accent5 });
  });
  s.addNotes("Outcomes for live submissions depend on Gemini's confidence: a duplicate below 0.85 routes to a human, which is the designed behaviour. Resubmitting Meera demonstrates the duplicate-refund guard.");

  // 8 Safety -----------------------------------------------------------------------------
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Demo" });
  s.addText("Safeguards and human-in-the-loop", { placeholder: "title" });
  const safe = [
    [fa.FaLock, "Reviewer sign-in", "Server-side identity from a reviewer key; client names ignored (prototype, not SSO)"],
    [fa.FaCopy, "One refund per transaction", "A second dispute on the same transaction always goes to a human"],
    [fa.FaUserShield, "PII masked before the model", "Cards, phones, Aadhaar, PAN, OTP, CVV, UPI: regex, best effort"],
    [fa.FaExclamationTriangle, "Prompt injection", "Detected heuristically and escalated; text can't set policy or amounts"],
    [fa.FaHistory, "Full audit trail", "Every step, engine, retry, review and reopen is recorded"],
    [fa.FaRedo, "Bounded AI retries", "429/503 retried with backoff; failure sends the case to a person, never to a fake answer"],
  ];
  for (let i = 0; i < safe.length; i++) {
    const x = 0.5 + (i % 2) * 4.6, y = 1.25 + Math.floor(i / 2) * 1.22;
    await circleIcon(s, safe[i][0], x, y + 0.05, 0.6, HEX.accent1);
    txt(s, safe[i][1], { x: x + 0.8, y, w: 3.6, h: 0.35, fontSize: 15, bold: true, color: C.text2 });
    txt(s, safe[i][2], { x: x + 0.8, y: y + 0.38, w: 3.6, h: 0.7, fontSize: 12 });
  }
  s.addNotes("Be explicit that detection is heuristic; the real protection is that the decision is computed from database evidence.");

  // 9 Stack & evaluation ------------------------------------------------------------------
  pres.addSection({ title: "Close" });
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Close" });
  s.addText("Implementation and honest evaluation", { placeholder: "title" });
  s.addChart(pres.charts.BAR, [{ name: "Offline rules engine", labels: ["Synthetic (n=100)", "Hand-authored (n=33)"], values: [99, 83.3] }], {
    x: 0.5, y: 1.25, w: 4.6, h: 3.4, barDir: "col", showTitle: true, title: "Reason-code accuracy, offline engine (%)",
    titleFontSize: 13, titleColor: HEX.dk2, titleFontFace: "+mn-lt", showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelFormatCode: "0.0",
    dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt", chartColors: [HEX.accent1], showLegend: false, valAxisMaxVal: 100, valAxisMinVal: 0,
    valAxisLabelColor: HEX.accent5, catAxisLabelColor: HEX.dk1, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
    valGridLine: { color: "E2E8F0", size: 0.5 }, catGridLine: { style: "none" },
  });
  card(s, 5.4, 1.25, 4.1, 1.5, HEX.lt2, "zero");
  txt(s, "0", { x: 5.65, y: 1.35, w: 1.0, h: 1.0, fontSize: 54, bold: true, color: C.accent1, fontFace: THEME.headFontFace, valign: "middle" });
  txt(s, "unsafe auto-resolutions across both suites", { x: 6.65, y: 1.5, w: 2.7, h: 0.8, fontSize: 14, bold: true, color: C.text2, valign: "middle" });
  txt(s, [
    { text: "Synthetic suite is circular (templates share keywords with the rules)", options: { bullet: true, breakLine: true } },
    { text: "Live Gemini accuracy not yet measured", options: { bullet: true, breakLine: true } },
    { text: "Stack: React, FastAPI, LangGraph, PostgreSQL, Gemini; 345 backend + 28 frontend tests in CI", options: { bullet: true } },
  ], { x: 5.4, y: 2.95, w: 4.1, h: 1.9, fontSize: 12, paraSpaceAfter: 4 });
  s.addNotes("Never present the 99% as Gemini accuracy.");

  // 10 Impact & roadmap -------------------------------------------------------------------
  s = pres.addSlide({ masterName: "Title Dark", sectionTitle: "Close" });
  s.addText("Humans decide the risky cases", { placeholder: "title" });
  s.addText("Code enforces policy. Every action is auditable.", { placeholder: "body" });
  txt(s, [
    { text: "Limitations: ", options: { bold: true, color: C.background1 } },
    { text: "prototype auth, regex PII masking, illustrative taxonomy, no live-model accuracy yet", options: { color: C.background2, breakLine: true } },
    { text: "Next: ", options: { bold: true, color: C.background1 } },
    { text: "SSO and roles, core-banking hooks, network rules, live evaluation on consented data, semantic retrieval", options: { color: C.background2 } },
  ], { x: 0.6, y: 3.7, w: 8.8, h: 1.3, fontSize: 14, paraSpaceAfter: 6 });
  s.addNotes("Close on the design principle, then invite questions.");

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
