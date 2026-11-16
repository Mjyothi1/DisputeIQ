const pptxgen = require('pptxgenjs');
const IMG = '/home/user/DisputeIQ/docs/zeta-2026/img/';
const OUT = process.argv[2];
const C = { bg:'0A1530', bg2:'0F1D44', panel:'14264F', line:'24407A', blue:'2F6BFF', cyan:'22D3EE', white:'FFFFFF', mut:'A9B8D6', amber:'F5B83D', green:'34D399', red:'F87171' };
const F = 'Calibri';
const p = new pptxgen(); p.layout = 'LAYOUT_16x9'; p.title = 'DisputeIQ - Zeta Innovate 2026'; p.author = 'DisputeIQ team';
let n = 0;
function base(title, kicker, notes) {
  const s = p.addSlide(); n++; s.background = { color: C.bg };
  s.addShape('rect', { x:0, y:0, w:0.12, h:5.625, fill:{ color:C.blue }, line:{ color:C.blue } });
  s.addShape('rect', { x:0, y:0, w:0.12, h:1.1, fill:{ color:C.cyan }, line:{ color:C.cyan } });
  if (kicker) s.addText(kicker.toUpperCase(), { x:0.5, y:0.28, w:8, h:0.25, fontFace:F, fontSize:10.5, bold:true, color:C.cyan, charSpacing:3, margin:0 });
  s.addText(title, { x:0.5, y:0.52, w:9, h:0.6, fontFace:F, fontSize:27, bold:true, color:C.white, margin:0 });
  s.addText('DisputeIQ  |  Zeta Innovate 2026', { x:0.5, y:5.28, w:5, h:0.25, fontFace:F, fontSize:9, color:C.mut, margin:0 });
  s.addText(String(n), { x:9.0, y:5.28, w:0.5, h:0.25, fontFace:F, fontSize:9, color:C.mut, align:'right', margin:0 });
  if (notes) s.addNotes(notes);
  return s;
}
function card(s, x, y, w, h, fill) { s.addShape('roundRect', { x, y, w, h, rectRadius:0.08, fill:{ color: fill || C.panel }, line:{ color:C.line, width:0.75 } }); }
function shot(s, file, x, y, w, h, cap) {
  s.addShape('roundRect', { x:x-0.04, y:y-0.04, w:w+0.08, h:h+0.08, rectRadius:0.06, fill:{ color:C.line }, line:{ color:C.cyan, width:0.75 } });
  s.addImage({ path: IMG + file, x, y, w, h });
  if (cap) s.addText(cap, { x, y:y+h+0.07, w, h:0.22, fontFace:F, fontSize:9, italic:true, color:C.mut, margin:0 });
}
function pill(s, text, x, y, w, color) {
  s.addShape('roundRect', { x, y, w, h:0.3, rectRadius:0.15, fill:{ color: color || C.blue }, line:{ color: color || C.blue } });
  s.addText(text, { x, y, w, h:0.3, fontFace:F, fontSize:10.5, bold:true, color:C.white, align:'center', valign:'middle', margin:0 });
}
function bullets(s, items, x, y, w, h, size) {
  s.addText(items.map((t, i) => ({ text: t, options: { bullet:{ code:'25AA', indent:14 }, breakLine: i < items.length - 1, paraSpaceAfter:7 } })), { x, y, w, h, fontFace:F, fontSize:size || 14, color:C.white, valign:'top', margin:0 });
}
const FOOT_LOCAL = 'Screenshots: running app built from commit 332f754 (local run, offline rule engine, synthetic data).';

// 1 Title
{
  const s = p.addSlide(); n++; s.background = { color: C.bg };
  s.addShape('rect', { x:0, y:0, w:10, h:5.625, fill:{ color:C.bg }, line:{ color:C.bg } });
  s.addShape('ellipse', { x:6.3, y:-1.4, w:5.5, h:5.5, fill:{ color:C.bg2 }, line:{ color:C.line, width:1 } });
  s.addShape('ellipse', { x:7.2, y:-0.5, w:3.6, h:3.6, fill:{ color:C.panel }, line:{ color:C.blue, width:1 } });
  s.addText('ZETA INNOVATE 2026', { x:0.7, y:1.0, w:6, h:0.3, fontFace:F, fontSize:12, bold:true, color:C.cyan, charSpacing:4, margin:0 });
  s.addText('DisputeIQ', { x:0.7, y:1.4, w:7, h:1.0, fontFace:F, fontSize:60, bold:true, color:C.white, margin:0 });
  s.addText('AI-Powered Dispute Resolution Platform', { x:0.7, y:2.4, w:7.5, h:0.5, fontFace:F, fontSize:24, color:C.mut, margin:0 });
  s.addShape('rect', { x:0.7, y:3.1, w:1.2, h:0.05, fill:{ color:C.cyan }, line:{ color:C.cyan } });
  s.addText('AI understands and drafts. Deterministic code decides. A human approves.', { x:0.7, y:3.3, w:7.5, h:0.4, fontFace:F, fontSize:15, italic:true, color:C.white, margin:0 });
  s.addText('Live app: dispute-iq-beryl.vercel.app   |   Code: github.com/Mjyothi1/DisputeIQ (main @ 332f754)', { x:0.7, y:4.9, w:9, h:0.3, fontFace:F, fontSize:10.5, color:C.mut, margin:0 });
  s.addNotes('Open with the one-line principle. Then say: this is a working product, not a mock-up - I will show it live.');
}

// 2 Problem
{
  const s = base('Card disputes are slow, manual and risky', 'The problem',
    'Issuers get thousands of disputes. Every one needs a transaction lookup, evidence checks, a reason code, a deadline check, a decision and two documents. Analysts spend most of their time on routine cases, and a missed deadline loses the customer\'s money. Customers also submit vague or incomplete complaints, which means slow back-and-forth.');
  const items = [
    ['Manual investigation', 'Each case: look up the transaction, run checks, pick a reason code'],
    ['Deadline risk', 'Windows are strict; a late filing means the case cannot proceed'],
    ['Incomplete complaints', 'Customers omit merchant, amount or card details, so analysts must chase them'],
    ['Routine work crowds out hard cases', 'Duplicate charges and failed ATM withdrawals look alike every time'],
  ];
  items.forEach((it, i) => {
    const x = 0.5 + (i % 2) * 4.55, y = 1.5 + Math.floor(i / 2) * 1.75;
    card(s, x, y, 4.3, 1.55);
    s.addText(String(i + 1).padStart(2, '0'), { x:x+0.2, y:y+0.15, w:0.7, h:0.4, fontFace:F, fontSize:22, bold:true, color:C.cyan, margin:0 });
    s.addText(it[0], { x:x+0.2, y:y+0.6, w:3.9, h:0.3, fontFace:F, fontSize:15, bold:true, color:C.white, margin:0 });
    s.addText(it[1], { x:x+0.2, y:y+0.92, w:3.9, h:0.55, fontFace:F, fontSize:11.5, color:C.mut, margin:0, valign:'top' });
  });
  s.addText('Illustrative taxonomy and time windows in this prototype; not a card-network rulebook. All data is synthetic.', { x:0.5, y:5.0, w:9, h:0.25, fontFace:F, fontSize:9.5, italic:true, color:C.mut, margin:0 });
}

// 3 Solution
{
  const s = base('One platform: customer portal + AI agent + reviewer desk', 'Proposed solution',
    'The core design principle: the LLM only reads language - it classifies and writes. Everything that moves money or time - eligibility, deadlines, amounts, duplicate detection, routing - is plain, unit-tested Python. And a human reviewer approves anything that is not a clear-cut low-value refund. No payment is executed anywhere; DisputeIQ recommends.');
  const cols = [
    ['Customer portal', 'Report a problem on your own transactions, or enter details manually. Track status and read the bank\'s letter.', C.blue],
    ['AI agent (9-step pipeline)', 'Masks PII, extracts claim facts, matches the transaction, runs evidence checks, classifies, drafts.', C.cyan],
    ['Reviewer desk', 'Queue by deadline, evidence checklist, recommendation, editable letter, full audit trail.', C.blue],
  ];
  cols.forEach((c, i) => {
    const x = 0.5 + i * 3.08;
    card(s, x, 1.45, 2.9, 2.15);
    s.addShape('rect', { x, y:1.45, w:2.9, h:0.07, fill:{ color:c[2] }, line:{ color:c[2] } });
    s.addText(c[0], { x:x+0.2, y:1.65, w:2.5, h:0.4, fontFace:F, fontSize:15.5, bold:true, color:C.white, margin:0 });
    s.addText(c[1], { x:x+0.2, y:2.1, w:2.5, h:1.4, fontFace:F, fontSize:11.5, color:C.mut, margin:0, valign:'top' });
  });
  card(s, 0.5, 3.85, 8.95, 1.15, C.bg2);
  s.addText([
    { text:'Who decides what', options:{ bold:true, color:C.cyan, breakLine:true } },
    { text:'LLM: understand the complaint, classify, write prose.   Python: deadlines, eligibility, amounts, duplicates, routing.   Human: every rejection and anything not clear-cut.', options:{ color:C.white } },
  ], { x:0.75, y:3.95, w:8.5, h:0.95, fontFace:F, fontSize:12.5, margin:0, valign:'middle' });
}

// 4 Customer portal
{
  const s = base('Customer portal: report a problem in under a minute', 'Customer experience',
    'Customers sign in, see their own transactions and cards, and choose which transaction is wrong. If they cannot find it, they enter details manually. The latest change: the card\'s last four digits are now mandatory for manual entry. Show the disabled button with three digits. This is enforced in the form and again on the server, where the API returns a 422 if last4 is missing.');
  shot(s, '03-cust-dashboard.png', 0.5, 1.4, 3.9, 2.44, 'Customer home: own cards and transactions');
  shot(s, '06-report-3digits-disabled.png', 4.7, 1.4, 3.9, 2.44, 'Manual entry: Submit stays disabled with 3 digits');
  card(s, 0.5, 4.2, 8.1, 0.95, C.bg2);
  s.addText([
    { text:'NEW  ', options:{ bold:true, color:C.cyan } },
    { text:'Card last 4 digits is required for manual entry: form disables Submit until 4 digits are typed; the API rejects a missing value (HTTP 422) and enforces ^\\d{4}$.', options:{ color:C.white } },
  ], { x:0.7, y:4.25, w:7.7, h:0.85, fontFace:F, fontSize:12, margin:0, valign:'middle' });
  pill(s, 'Own data only', 8.85, 1.5, 0.95, C.blue);
  s.addText('Customer-entered details are labelled NOT BANK-VERIFIED for the reviewer.', { x:8.8, y:1.95, w:1.1, h:2.0, fontFace:F, fontSize:9.5, color:C.mut, margin:0, valign:'top' });
}

// 5 AI pipeline
{
  const s = base('The AI agent: a nine-step, fully audited pipeline', 'AI-powered complaint analysis',
    'This is a LangGraph state graph. Steps with the robot marker use the LLM; the rest are deterministic. 1 mask PII before any model sees text. 2 extract claim facts with a schema-validated structured output. 3 match to a transaction by amount, merchant and date. 4 run evidence checks - duplicate, strong authentication, refund issued, subscription cancelled, ATM failure, amount mismatch, dispute history. 5 classify the reason code. 6 eligibility and deadline check in Python. 7 recommend: policy is Python; the LLM only writes the rationale and can only lower confidence. 8 draft the letter and, where relevant, the chargeback filing, with placeholders filled from the database. 9 route: auto-resolve or human review. Every step writes an audit event. Honest note: the numbers I show later are from the offline rule engine; Gemini is the configured live provider.');
  const steps = [
    ['1','Mask PII',0],['2','Extract claim',1],['3','Match txn',0],['4','Evidence checks',0],['5','Classify reason',1],
    ['6','Eligibility',0],['7','Recommend',2],['8','Draft docs',1],['9','Route',0],
  ];
  const col = (k) => k === 1 ? C.cyan : k === 2 ? C.amber : C.blue;
  steps.forEach((st, i) => {
    const row = i < 5 ? 0 : 1; const idx = row === 0 ? i : i - 5; const x = (row === 0 ? 0.5 : 1.3) + idx * 1.8; const y = row === 0 ? 1.5 : 2.9;
    card(s, x, y, 1.6, 1.0);
    s.addShape('ellipse', { x:x+0.1, y:y+0.1, w:0.32, h:0.32, fill:{ color:col(st[2]) }, line:{ color:col(st[2]) } });
    s.addText(st[0], { x:x+0.1, y:y+0.1, w:0.32, h:0.32, fontFace:F, fontSize:11, bold:true, color:C.bg, align:'center', valign:'middle', margin:0 });
    s.addText(st[1], { x:x+0.08, y:y+0.5, w:1.45, h:0.45, fontFace:F, fontSize:12.5, bold:true, color:C.white, margin:0, valign:'middle' });
    if (idx < (row === 0 ? 4 : 3)) s.addText('>', { x:x+1.6, y:y+0.3, w:0.2, h:0.3, fontFace:F, fontSize:14, bold:true, color:C.cyan, align:'center', margin:0 });
  });
  s.addText('>', { x:9.05, y:1.8, w:0.3, h:0.3, fontFace:F, fontSize:14, bold:true, color:C.cyan, margin:0 });
  pill(s, 'LLM step', 0.5, 4.2, 1.1, C.cyan); pill(s, 'Policy + LLM rationale', 1.75, 4.2, 2.1, C.amber); pill(s, 'Deterministic code', 4.0, 4.2, 1.7, C.blue);
  s.addText('Eight reason codes (e.g. duplicate, ATM cash, fraud, goods not received). Policy decides the action; the model can only lower confidence. Every step logs an audit event.', { x:0.5, y:4.65, w:9, h:0.45, fontFace:F, fontSize:11.5, color:C.mut, margin:0 });
}

// 6 Reviewer
{
  const s = base('Reviewer desk: evidence already assembled', 'Reviewer dashboard and investigation',
    'The reviewer signs in with an access key issued server-side - the reviewer name comes from the server, not from what you type. The queue sorts by deadline. Open a case: the complaint is shown masked, the matched transaction, evidence checks with pass/fail verdicts, the recommendation, the reasons it needs a human, and an editable draft letter. The right panel says explicitly: a recommendation, not yet approved - nothing is sent until you decide. Options: approve, approve with edits, override, reject. Here the friendly-fraud case: the customer says "not me" but the transaction was OTP-authenticated, so the agent recommends reject and flags it for a person.');
  shot(s, '11-queue.png', 0.5, 1.4, 4.4, 2.75, 'Queue: sorted by deadline, filters, confidence meter');
  shot(s, '12-case-friendly.png', 5.1, 1.4, 4.4, 2.75, 'Case: OTP-authenticated "not me" claim is flagged');
  const f = [['Recommendation, not action', 'Nothing is sent until a reviewer decides'], ['Evidence verdicts', 'Strong authentication shown as a failed check on a fraud claim'], ['Audit trail', 'Each pipeline step logged with model, tokens and latency']];
  f.forEach((t, i) => {
    const x = 0.5 + i * 3.08; card(s, x, 4.4, 2.9, 0.75, C.bg2);
    s.addText([{ text:t[0], options:{ bold:true, color:C.cyan, breakLine:true } }, { text:t[1], options:{ color:C.mut } }], { x:x+0.12, y:4.42, w:2.7, h:0.71, fontFace:F, fontSize:10.5, margin:0, valign:'middle' });
  });
}

// 7 Need more info
{
  const s = base('Need More Info: ask for exactly what is missing', 'Intelligent workflow  |  latest change',
    'This is the latest merged change. Before, the need-more-info letter always said send merchant, amount and date. Now the letter is built from the case. If the transaction could not be identified, it asks only for the details the customer did not already give, plus a screenshot or statement line and why they believe the charge is wrong. If the transaction is identified but the claim is thin, it asks for evidence matching the dispute type - for goods not received: order number, promised delivery date, messages with the merchant. Every letter warns the customer never to share their full card number, CVV, PIN or OTP. Important accuracy points: the list is chosen by deterministic code, not generated by the model; the letter is a draft the reviewer approves - the customer sees it in the portal after approval; DisputeIQ does not send real email for this letter.');
  shot(s, '18-cust-moreinfo.png', 0.5, 1.4, 4.1, 2.72, 'What the customer sees after the reviewer approves');
  card(s, 4.85, 1.4, 4.65, 2.72, '0C1838');
  s.addText([
    { text:'Matched "Goods not received" case (letter builder output)', options:{ bold:true, color:C.cyan, fontSize:9.5, breakLine:true } },
    { text:'Please reply with:', options:{ color:C.white, breakLine:true } },
    { text:'  - Your order number or booking reference and the date you ordered', options:{ color:C.white, breakLine:true } },
    { text:'  - The delivery date you were promised, and what has (or has not) arrived', options:{ color:C.white, breakLine:true } },
    { text:'  - Any messages or emails with the merchant about the missing item or service', options:{ color:C.white, breakLine:true } },
    { text:' ', options:{ breakLine:true } },
    { text:'For your security, never send your full card number, CVV, PIN or OTP.', options:{ color:C.amber, bold:true } },
  ], { x:5.0, y:1.5, w:4.35, h:2.55, fontFace:'Consolas', fontSize:10.5, margin:0, valign:'top' });
  const t = [['Transaction not found', 'Asks only for the details not already given'], ['Transaction found, claim thin', 'Evidence for the dispute type (8 reason codes)'], ['Every letter', 'Never share full card number, CVV, PIN or OTP']];
  t.forEach((q, i) => {
    const x = 0.5 + i * 3.08; card(s, x, 4.4, 2.9, 0.75, C.bg2);
    s.addText([{ text:q[0], options:{ bold:true, color:C.cyan, breakLine:true } }, { text:q[1], options:{ color:C.mut } }], { x:x+0.12, y:4.42, w:2.7, h:0.71, fontFace:F, fontSize:10.5, margin:0, valign:'middle' });
  });
}

// 8 Architecture
{
  const s = base('Architecture and technology stack', 'System design',
    'Three tiers. React with TypeScript and Vite on Vercel. FastAPI on Render. SQLAlchemy with Alembic migrations; PostgreSQL with pgvector in the deployed setup, SQLite for no-Docker local runs. The agent is a LangGraph state graph. The LLM provider is pluggable - Gemini via google-genai by default, with Anthropic and OpenAI available as alternates, and an offline rule engine used for tests. Retrieval of similar past cases uses pgvector on Postgres; the default embedder is a lexical hash, not semantic. Be upfront that Langfuse tracing is optional and off by default. The deployed free tier sleeps after idle, so the first request can take about a minute.');
  const box = (x, y, w, h, title, sub, color) => {
    card(s, x, y, w, h); s.addShape('rect', { x, y, w:0.07, h, fill:{ color }, line:{ color } });
    s.addText([{ text:title, options:{ bold:true, color:C.white, fontSize:13, breakLine:true } }, { text:sub, options:{ color:C.mut, fontSize:10 } }], { x:x+0.2, y:y+0.05, w:w-0.3, h:h-0.1, fontFace:F, margin:0, valign:'middle' });
  };
  box(0.5, 1.45, 2.4, 1.0, 'React + TypeScript', 'Vite, Tailwind, TanStack Query. Customer and reviewer portals', C.blue);
  box(3.4, 1.45, 2.4, 1.0, 'FastAPI', 'REST, role-based auth, rate limits, Pydantic schemas', C.blue);
  box(6.3, 1.45, 3.2, 1.0, 'LangGraph agent', '9 audited nodes; schema-validated LLM calls', C.cyan);
  box(0.5, 3.0, 2.4, 1.0, 'Rules engine (Python)', 'Eligibility, policy, routing; thresholds in one YAML', C.amber);
  box(3.4, 3.0, 2.4, 1.0, 'Evidence tools', 'Duplicate, auth, refund, subscription, ATM, amount', C.amber);
  box(6.3, 3.0, 3.2, 1.0, 'LLM provider (pluggable)', 'Gemini (default) / Anthropic / OpenAI / offline mock', C.cyan);
  box(0.5, 4.3, 4.4, 0.8, 'Data', 'PostgreSQL + pgvector (deployed) | SQLite (local) | Alembic', C.blue);
  box(5.1, 4.3, 4.4, 0.8, 'Hosting', 'Vercel (frontend) | Render (API + Postgres)', C.blue);
  [[2.9, 1.95], [5.8, 1.95]].forEach(([x, y]) => s.addText('>', { x, y:y-0.15, w:0.5, h:0.3, fontFace:F, fontSize:16, bold:true, color:C.cyan, align:'center', margin:0 }));
}

// 9 Security & HITL
{
  const s = base('Safety by design: code gates, human approval', 'Security, reliability and human-in-the-loop',
    'Walk through the auto-resolve gate: all five must hold. Confidence at least 0.85; amount at most 10,000 rupees; reason code is duplicate charge or ATM cash not dispensed; the recommendation is refund with all checks clear; no injection flag, no friendly-fraud flag, no other dispute on the same transaction. Everything else goes to a person. Every rejection goes to a person. Be honest on limits: prototype reviewer auth with static keys, regex-based PII masking and injection detection - defence in depth, not a guarantee. No refund or payment is executed anywhere.');
  card(s, 0.5, 1.4, 4.55, 3.7);
  s.addText('Auto-resolve only if ALL hold', { x:0.7, y:1.5, w:4.2, h:0.3, fontFace:F, fontSize:14, bold:true, color:C.cyan, margin:0 });
  bullets(s, ['Confidence at least 0.85', 'Amount at most INR 10,000', 'Duplicate charge or ATM cash only', 'Recommendation is REFUND, checks clear', 'No injection or friendly-fraud flag', 'No other dispute on the same transaction'], 0.7, 1.9, 4.2, 2.4, 12.5);
  s.addText('Anything else, and every rejection, goes to a human.', { x:0.7, y:4.4, w:4.2, h:0.55, fontFace:F, fontSize:12, bold:true, color:C.amber, margin:0, valign:'middle' });
  const r = [['PII masked before the LLM', 'Cards, UPI, mobiles, CVV, OTP and more (regex, best effort)'], ['Prompt-injection defence', 'Delimited text + detector + schema output; code owns the decision'], ['Letters cannot invent figures', 'Amounts and dates filled from the database; model text with literals is rejected'], ['Auth and access', 'Reviewer keys; customer scrypt-hashed passwords; per-account data isolation']];
  r.forEach((q, i) => {
    const y = 1.4 + i * 0.95; card(s, 5.25, y, 4.25, 0.85, C.bg2);
    s.addText([{ text:q[0], options:{ bold:true, color:C.white, fontSize:12, breakLine:true } }, { text:q[1], options:{ color:C.mut, fontSize:10 } }], { x:5.4, y:y+0.03, w:4.0, h:0.79, fontFace:F, margin:0, valign:'middle' });
  });
}

// 10 Verified & honest
{
  const s = base('What we verified, and what we do not claim', 'Evidence and honesty',
    'Say plainly: 413 backend tests and 67 frontend tests passed on the code including the latest change. The evaluation numbers are from the offline rule engine, and the synthetic suite is circular - it shows pipeline consistency, not language understanding. The hand-authored suite is small and written by an AI assistant. The property that matters is the safety invariant: zero unsafe auto-resolutions in both suites. No live-Gemini accuracy number has been measured. Judges respect that you know the limits.');
  const stats = [['413', 'backend tests passing'], ['67', 'frontend tests passing'], ['0', 'unsafe auto-resolutions (133 cases)'], ['6/6', 'adversarial complaints flagged']];
  stats.forEach((q, i) => {
    const x = 0.5 + i * 2.3; card(s, x, 1.4, 2.15, 1.35);
    s.addText(q[0], { x, y:1.5, w:2.15, h:0.7, fontFace:F, fontSize:38, bold:true, color:C.cyan, align:'center', margin:0 });
    s.addText(q[1], { x:x+0.1, y:2.2, w:1.95, h:0.5, fontFace:F, fontSize:11, color:C.mut, align:'center', margin:0 });
  });
  card(s, 0.5, 3.0, 4.5, 2.1);
  s.addText('Offline rule-engine evals (mock, not Gemini)', { x:0.7, y:3.08, w:4.2, h:0.3, fontFace:F, fontSize:12.5, bold:true, color:C.white, margin:0 });
  bullets(s, ['Synthetic 100 cases: reason code 99%, decision 99% (circular)', 'Hand-authored 33 cases: reason code 83.3% (20/24), routing 87.9%', 'Safety property holds in both: 0 unsafe auto-resolutions'], 0.7, 3.45, 4.2, 1.6, 11);
  card(s, 5.2, 3.0, 4.3, 2.1, C.bg2);
  s.addText('Not claimed', { x:5.4, y:3.08, w:4.0, h:0.3, fontFace:F, fontSize:12.5, bold:true, color:C.amber, margin:0 });
  bullets(s, ['No live-Gemini accuracy number', 'No payment or refund is executed', 'Prototype auth, not SSO; regex PII masking', 'Simplified taxonomy, synthetic data'], 5.4, 3.45, 4.0, 1.6, 11);
}

// 11 Advantages / applications / future
{
  const s = base('Why it stands out, where it applies, what is next', 'Competitive advantages and future scope',
    'Advantages are all things judges can check in the code: safety by construction, auditability, a working two-portal product, and a customer-facing letter that asks for the right evidence. Applications: card issuers, banks, payment apps and wallets, fintech support teams. Future scope is explicitly future - not built: SSO and MFA, live-Gemini evaluation on real-world style complaints, representment and network-specific rules, an actual payment integration with approvals, outbound email or SMS delivery, and a semantic embedder for similar-case retrieval.');
  card(s, 0.5, 1.4, 4.4, 3.7);
  s.addText('Competitive advantages', { x:0.7, y:1.5, w:4.0, h:0.3, fontFace:F, fontSize:14, bold:true, color:C.cyan, margin:0 });
  bullets(s, ['Safety by construction: LLM cannot change an action', 'Full audit trail on every step', 'Two working portals, one pipeline', 'Evidence-specific requests cut back-and-forth', 'Provider-agnostic; runs fully offline for tests'], 0.7, 1.9, 4.0, 3.1, 12);
  card(s, 5.1, 1.4, 4.4, 1.75, C.bg2);
  s.addText('Real-world applications', { x:5.3, y:1.5, w:4.0, h:0.3, fontFace:F, fontSize:14, bold:true, color:C.cyan, margin:0 });
  bullets(s, ['Card issuers and banks', 'Payment apps and wallets', 'Fintech support operations'], 5.3, 1.9, 4.0, 1.2, 12);
  card(s, 5.1, 3.35, 4.4, 1.75);
  s.addText('Future scope (not built)', { x:5.3, y:3.45, w:4.0, h:0.3, fontFace:F, fontSize:14, bold:true, color:C.amber, margin:0 });
  bullets(s, ['SSO / MFA; live-model evaluation', 'Network rulebooks and representment', 'Real email/SMS delivery; payment hooks'], 5.3, 3.85, 4.0, 1.2, 11.5);
}

// 12 Conclusion
{
  const s = p.addSlide(); n++; s.background = { color: C.bg };
  s.addShape('ellipse', { x:-1.5, y:2.6, w:5, h:5, fill:{ color:C.bg2 }, line:{ color:C.line } });
  s.addText('DisputeIQ', { x:0.7, y:0.9, w:8, h:0.8, fontFace:F, fontSize:44, bold:true, color:C.white, margin:0 });
  s.addText('A working dispute platform where the AI helps, the code decides, and a human approves.', { x:0.7, y:1.75, w:8.4, h:0.7, fontFace:F, fontSize:20, color:C.mut, margin:0 });
  const k = [['Working product', 'Customer and reviewer portals, live'], ['Engineered for trust', 'Deterministic gates, audit trail, tests'], ['Latest improvements', 'Mandatory card last 4; evidence-specific info requests']];
  k.forEach((q, i) => {
    const x = 0.7 + i * 2.95; card(s, x, 3.0, 2.75, 1.2);
    s.addText([{ text:q[0], options:{ bold:true, color:C.cyan, fontSize:13.5, breakLine:true } }, { text:q[1], options:{ color:C.white, fontSize:11.5 } }], { x:x+0.15, y:3.05, w:2.45, h:1.1, fontFace:F, margin:0, valign:'middle' });
  });
  s.addText('Thank you  |  dispute-iq-beryl.vercel.app  |  github.com/Mjyothi1/DisputeIQ', { x:0.7, y:4.7, w:8.6, h:0.3, fontFace:F, fontSize:12, color:C.mut, margin:0 });
  s.addNotes('Close on the three-part message. Invite questions.');
}
p.writeFile({ fileName: OUT }).then(() => console.log('ok'));
