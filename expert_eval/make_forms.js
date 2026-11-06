// Builds the expert rating form, in Indonesian (for the experts) and in English (a translation for readers of
// the replication package), and writes form_spec.json (the items and the Part B cases, read by analyse_expert.py).
// One anonymous form with no questions about the expert; every answer is a rating from 1 to 5 (Part A also
// allows TD = cannot judge):
//   before the briefing: consent only
//   after the briefing:  Part A (7 rule items on an appropriateness scale, 12 items and 1 attention check on an
//                        agreement scale); Part B (7 conditions the rules rate Moderate or Severe x 3 ratings,
//                        2 near-threshold conditions the rules rate Normal x 1 rating)
// Usage: NODE_PATH=<global node_modules> node make_forms.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, AlignmentType,
  PageOrientation, ShadingType, BorderStyle, LevelFormat, HeadingLevel,
} = require("docx");

const scen = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(__dirname, "scenarios.json"), "utf8")).map((s) => [s.id, s]));
const key = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(__dirname, "answer_key.json"), "utf8")).map((s) => [s.id, s]));
const shown = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(__dirname, "tasks_shown.json"), "utf8")).map((s) => [s.id, s]));
// Part B cases: every scenario the rules rate Moderate or Severe except S06, whose level, cause, possible cause and
// tasks equal those of S04; plus the two Normal scenarios closest to a Moderate limit (S01: THI 25.6, limit 26;
// S10: |T - T*| = 1.98 degC, limit 2).
const DROPPED = { S06: "same level, cause, possible cause and tasks as S04" };
const NORMAL_NEAR = ["S01", "S10"];
const CASE_IDS = Object.keys(scen).filter((id) => (shown[id] && !DROPPED[id]) || NORMAL_NEAR.includes(id)).sort();

const TASK_ID = {
  FANS: "Naikkan tahap kipas untuk menambah kecepatan angin", PADS: "Jalankan cooling pad setelah tahap kipas dinaikkan",
  PADC: "Periksa pompa dan distribusi air cooling pad", FANB: "Periksa kekencangan sabuk (belt) kipas, bersihkan kipas",
  INLT: "Atur bukaan inlet sesuai target kecepatan angin", MVCK: "Periksa laju ventilasi minimum",
  CHBH: "Periksa perilaku anak ayam di sekitar brooder", HEAT: "Pastikan pemanas/brooder menyala",
  HTSP: "Turunkan set point suhu brooding setelah pemeriksaan", MVUP: "Naikkan ventilasi minimum (≥ 1 dari 5 menit)",
  LITC: "Uji genggam litter, periksa kebocoran tempat minum", LITR: "Ganti litter basah dengan alas kering",
  AIRQ: "Ukur kualitas udara, sesuaikan ventilasi",
};
const PCAUSE_ID = {
  AIRF: "Aliran udara rendah (kipas, sabuk atau inlet)", HUMH: "Panas lembap: cooling pad akan menambah kelembapan",
  COOL: "Tahap pendinginan di bawah beban panas", HTRC: "Pemanas kurang atau udara dingin mengenai anak ayam",
  SETP: "Set point atau panas di atas target", WETL: "Litter basah, ventilasi minimum terlalu kecil",
  LITQ: "Kondisi litter (menggumpal atau menumpuk)", VENT: "Ventilasi di bawah kebutuhan udara segar",
};
const MODE = { preventive: ["tugas pencegahan", "preventive tasks"], corrective: ["tugas perbaikan", "corrective tasks"] };
const CAUSE = { thermal: ["termal", "thermal"], NH3: ["NH₃", "NH₃"], CO2: ["CO₂", "CO₂"] };
const KIND = { heat: ["panas, THI", "heat, THI"], hot: ["terlalu hangat untuk target", "too warm for the target"],
  cold: ["terlalu dingin untuk target", "too cold for the target"] };
const LEVEL = { Normal: ["Normal", "Normal"], Moderate: ["Sedang", "Moderate"], Severe: ["Berat", "Severe"] };
// Domain column of Part A (who can best judge an item): a closed-house operation, b broiler environment and heat
// stress, c SAP PM/ECC, d IS evaluation. Experts choose TD for items outside their field.
const FIELD = { ab: ["kandang", "house"], ad: ["kandang / SI", "house / IS"], ac: ["kandang / SAP", "house / SAP"],
  c: ["SAP", "SAP"], all: ["semua", "all"] };
// Part A. id, domains, Indonesian, English. R items are rated for appropriateness, the others for agreement.
// T5 and S5 are negatively worded risk items (reported as they are, never reversed and averaged); CHK is an
// attention check whose correct answer is disagreement (one notification needs three Severe episodes in 24 h).
const RULE_ITEMS = [
  ["R1", "ab", "Ambang NH₃: Sedang di atas 10 ppm, Berat di atas 20 ppm.", "NH₃ limits: Moderate above 10 ppm, Severe above 20 ppm."],
  ["R2", "ab", "Ambang CO₂: Sedang di atas 3.000 ppm, Berat di atas 3.500 ppm.", "CO₂ limits: Moderate above 3,000 ppm, Severe above 3,500 ppm."],
  ["R3", "ab", "Kelas THI mulai hari ke-21: Normal di bawah 26, Sedang 26–29, Berat di atas 29.", "THI classes from day 21: Normal below 26, Moderate 26–29, Severe above 29."],
  ["R4", "ab", "Sebelum hari ke-21, anak ayam dinilai dari selisih suhu terhadap target Ross menurut bobot sampel dan RH (Normal ≤ 2 °C, Sedang > 2–4 °C, Berat > 4 °C), bukan dari indeks panas.", "Before day 21, chicks are rated by the deviation from the Ross target by sample weight and RH (Normal ≤ 2 °C, Moderate > 2–4 °C, Severe > 4 °C), not by a heat index."],
  ["R5", "ab", "Aturan persistensi: tingkat zona naik setelah 2 jendela 5 menit berturut-turut dan turun setelah 3, sebagai keseimbangan antara kecepatan dan alarm palsu.", "Persistence rule: a zone level rises after 2 consecutive 5-minute windows and falls after 3, as a balance between speed and false alarms."],
  ["R6", "ab", "Lima parameter (suhu, RH, CO₂, NH₃, kecepatan angin) untuk menilai kondisi hidup ayam di kandang.", "Five parameters (temperature, RH, CO₂, NH₃, air speed) to judge the birds' living conditions."],
  ["R7", "ab", "Tiga zona (inlet, tengah, exhaust) untuk mewakili kondisi sepanjang kandang 120 m.", "Three zones (inlet, middle, exhaust) to represent conditions along a 120 m house."],
];
const AGREE_ITEMS = [
  ["T1", "ad", "Keluaran berupa tingkat dan penyebab (misalnya “Berat – NH₃”) mudah dipahami kepala kandang.", "The output as level and cause (e.g. “Severe – NH₃”) is easy for the farm head to understand."],
  ["T2", "ab", "Kemungkinan penyebab yang ditampilkan bersama setiap penilaian (misalnya “set point atau panas di atas target”) mengarahkan kepala kandang ke bagian yang tepat untuk diperiksa.", "The possible cause shown with each rating (e.g. “set point or heat above the target”) points the farm head to the right thing to check."],
  ["T3", "ab", "Tugas pertama yang disarankan aman dilakukan, tanpa menimbulkan risiko baru bagi ayam atau peralatan.", "The first tasks suggested are safe to carry out, without creating new risks for the birds or the equipment."],
  ["T4", "ab", "Sumber yang dicantumkan pada setiap tugas membuat staf lebih yakin untuk menjalankannya.", "The source given with each task makes staff more confident to carry it out."],
  ["T5", "ab", "Jumlah pemberitahuan, peringatan dan tugas dari sistem ini berisiko terlalu banyak sehingga staf mulai mengabaikannya.", "The number of notices, alerts and tasks from this system risks being so high that staff start to ignore them."],
  ["CHK", "all", "Sistem membuka satu notifikasi SAP PM setiap kali satu zona dinilai Berat.", "The system opens one SAP PM notification every time a zone is rated Severe."],
  ["S1", "ac", "Satu notifikasi SAP PM setelah tiga episode Berat di satu zona dalam 24 jam adalah tingkat eskalasi yang tepat: tidak terlalu cepat dan tidak terlalu lambat.", "One SAP PM notification after three Severe episodes in a zone within 24 hours is the right level of escalation: neither too early nor too late."],
  ["S2", "c", "Bagian SAP (tabel kustom, satu function module RFC, user teknis) dapat diterapkan pada SAP ECC 6.0 tanpa memodifikasi objek standar SAP.", "The SAP part (custom table, one RFC-enabled function module, technical user) can be implemented in SAP ECC 6.0 without modifying standard SAP objects."],
  ["S3", "ac", "Mencatat di SAP PM apakah setiap tugas sudah dikerjakan bermanfaat bagi technical service untuk mengevaluasi tindakan di kandang.", "Recording in SAP PM whether each task was done helps technical service evaluate the actions taken in the house."],
  ["S4", "ac", "Laporan harian per kandang di SAP (status tugas dan apakah kondisi kembali Normal) cukup untuk menilai apakah tindakan berhasil.", "The daily SAP report per house (task status and whether conditions returned to Normal) is enough to judge whether the actions worked."],
  ["S5", "ac", "Kewajiban menandai tugas selesai di SAP PM akan menjadi beban administrasi yang sulit dipenuhi staf atau kantor farm.", "Having to mark tasks done in SAP PM would be an administrative burden that staff or the farm office could hardly meet."],
  ["G1", "ac", "Alur kerja sistem ini sesuai dengan SOP dan pembagian peran di farm closed house yang saya kenal.", "The workflow of this system fits the SOPs and roles of the closed-house farms I know."],
  ["G2", "all", "Saya akan mendukung uji coba (pilot) sistem ini di kandang closed house.", "I would support a pilot of this system in a closed house."],
];
// Summary of the design: the bullets of the earlier Form 2, unchanged
const SUMMARY = [
  ["Sensor suhu, kelembapan dan CO₂ di tiga zona (inlet, tengah, exhaust), dua sensor NH₃ dan satu sensor kecepatan angin terhubung ke satu Raspberry Pi melalui satu kabel RS-485 (Modbus).",
   "Temperature, humidity and CO₂ sensors in three zones (inlet, middle, exhaust), two NH₃ sensors and one air-speed sensor share one RS-485 cable (Modbus) to a Raspberry Pi."],
  ["Setiap 5 menit Raspberry Pi menilai setiap zona Normal, Sedang atau Berat beserta penyebabnya, menurut tabel di bawah (sumber: Ross broiler guide, aturan UE, studi THI daerah tropis lembap). Pembacaan NH₃ yang berada dalam galat sensor ±5 ppm dari batas kelas meminta pemeriksaan dengan kertas indikator.",
   "Every 5 minutes the Raspberry Pi rates each zone Normal, Moderate or Severe with its cause, using the table below (sources: Ross broiler guide, EU rules, a humid-tropics THI study). An NH₃ reading within the sensor's ±5 ppm error of a class limit asks for a check with indicator paper."],
  ["Tingkat zona naik hanya setelah dua jendela 5 menit berturut-turut dan turun setelah tiga, untuk mengurangi alarm palsu. Kepala kandang mendapat pemberitahuan pencegahan beserta tugas saat kandang menjadi Sedang, dan peringatan beserta tugas perbaikan saat episode Berat dimulai, juga tanpa internet.",
   "A zone's level rises only after two consecutive 5-minute windows and falls after three, to reduce false alarms. The farm head gets a preventive notice with tasks when the house becomes Moderate, and an alert with corrective tasks when a Severe episode starts, also without internet."],
  ["Setiap penilaian dikirim melalui layanan middleware dan dicatat sekali di SAP ECC 6.0 (tabel kustom) oleh satu function module; data yang tertunda disimpan lokal dan dikirim ulang tanpa duplikasi.",
   "Every assessment is sent through a middleware service and recorded once in SAP ECC 6.0 (custom table) by one function module; pending data are stored locally and resent without duplicates."],
  ["Bersama setiap penilaian Sedang atau Berat, sistem menampilkan kemungkinan penyebab (petunjuk berbasis aturan, bukan diagnosis) dan hingga tiga tugas pertama: tugas pencegahan pada tingkat Sedang, tugas perbaikan pada tingkat Berat, masing-masing dengan sumbernya (Ross handbook, UGA extension, Medion). Tugas pertama biasanya pemeriksaan. Tugas hanya saran; controller kandang tetap mengendalikan peralatan.",
   "With each Moderate or Severe rating the system shows a possible cause (a rule-based hint, not a diagnosis) and up to three first tasks: preventive at Moderate, corrective at Severe, each with its source (Ross handbook, UGA extension, Medion). The first is usually a check. Tasks are advice; the house controller still runs the equipment."],
  ["Tiga episode Berat di satu zona dalam 24 jam membuka satu notifikasi SAP Plant Maintenance (PM) pada functional location kandang, dengan tugas-tugasnya terlampir; staf menandai setiap tugas selesai di SAP PM, atau kantor farm melakukannya bila staf tidak memiliki akses SAP.",
   "Three Severe episodes in one zone within 24 hours open one SAP Plant Maintenance (PM) notification on the house's functional location, with the tasks attached; staff mark each task done in SAP PM, or the farm office does so where staff have no SAP access."],
  ["Setiap pagi SAP membuat laporan per kandang secara otomatis: kelengkapan data, kondisi, kemungkinan penyebab (penyebab yang berulang ditandai) dan pemeriksaan notifikasi (tugas selesai, belum selesai atau terlambat, dan apakah kondisi kembali Normal setelah tugas selesai).",
   "Every morning SAP creates a report per house automatically: data completeness, conditions, possible causes (a recurring cause is flagged) and a notification check (tasks done, open or overdue, and whether conditions returned to Normal after a task was done)."],
];

const FONT = "Arial";
const A4 = { width: 11906, height: 16838 };
const MARGIN = { top: 1000, bottom: 1000, left: 1134, right: 1134 };
const border = { style: BorderStyle.SINGLE, size: 4, color: "808080" };
const borders = { top: border, bottom: border, left: border, right: border };
const GREY = "E7E6E6";

function cases() {
  return CASE_IDS.map((id, i) => {
    const x = shown[id];
    return { case: `C${i + 1}`, scenario: id, level: x ? x.level : "Normal", normal: !x,
      possible_cause: x ? x.possible_cause : null, tasks: x ? x.tasks.map((t) => t.code) : [], rule_cause: key[id].rule_cause };
  });
}

function build(lang) {
  const L = (id, en) => (lang === "id" ? id : en);
  const k = lang === "id" ? 0 : 1;
  const t = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || 20, bold: o.bold, italics: o.italics });
  const p = (runs, o = {}) => new Paragraph({ children: Array.isArray(runs) ? runs : [runs], spacing: { after: o.after ?? 80 },
    alignment: o.align, keepNext: o.keepNext });
  const h = (text, o = {}) => new Paragraph({ heading: HeadingLevel.HEADING_2, keepNext: true, pageBreakBefore: o.pageBreak,
    spacing: { before: o.pageBreak ? 0 : 200, after: 100 }, children: [new TextRun({ text, font: FONT, size: 24, bold: true })] });
  const title = (text) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 }, children: [t(text, { size: 28, bold: true })] });
  const cell = (children, width, o = {}) => new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, margins: { top: 40, bottom: 40, left: 70, right: 70 },
    shading: o.fill ? { fill: o.fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    children: (Array.isArray(children) ? children : [children]).map((c) => (typeof c === "string"
      ? p(t(c, { size: o.size || 18, bold: o.bold, italics: o.italics }), { align: o.align, after: 0 }) : c)),
  });
  const hc = (text, width, o = {}) => cell(text, width, { fill: GREY, bold: true, size: 16, ...o });
  const table = (widths, rows) => new Table({ width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths, rows });
  const bullet = (text) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 40 }, children: [t(text, { size: 18 })] });
  const C = { align: AlignmentType.CENTER };

  // ------------------------------------------------ page 1: before the briefing
  const before = [
    title(L("Evaluasi Pakar — Formulir Penilaian", "Expert evaluation — Rating form")),
    p(t(L("Penelitian: rancangan sistem IoT yang menilai kondisi kandang broiler closed house, menyarankan tugas perbaikan dan mencatatnya di SAP ERP.",
      "Study: the design of an IoT system that rates conditions in closed broiler houses, suggests corrective tasks and records them in SAP ERP."), { size: 19 })),
    p(t(L("Versi rancangan: makalah v34, katalog tugas 2026-10-v2", "Design version: paper v34, task catalog 2026-10-v2"), { size: 16, italics: true }), { after: 60 }),
    h(L("Penjelasan dan persetujuan (diisi sebelum presentasi)", "Information and consent (before the presentation)")),
    bullet(L("Yang dievaluasi adalah rancangan penelitian, bukan Anda. Partisipasi sukarela, sekitar 35 menit termasuk presentasi; Anda boleh berhenti kapan saja tanpa alasan.",
      "We evaluate a research design, not you. Participation is voluntary and takes about 35 minutes including the presentation; you may stop at any time without giving a reason.")),
    bullet(L("Formulir ini anonim: tidak ada nama, kode atau data lain yang dapat mengenali Anda. Jawaban hanya dilaporkan secara agregat dalam publikasi ilmiah.",
      "This form is anonymous: no name, code or other detail that could identify you. Answers are reported only in aggregate in a scientific publication.")),
    bullet(L("Semua pertanyaan berupa penilaian 1–5. Kami justru mencari kelemahan rancangan: nilai rendah sama bergunanya dengan nilai tinggi.",
      "Every question is a rating from 1 to 5. We are looking for the design's weaknesses: low ratings are as useful as high ones.")),
    bullet(L("Tidak ada risiko yang diketahui dan data perusahaan tidak diminta. Karena anonim, jawaban tidak dapat ditarik setelah formulir diserahkan. Pertanyaan dapat diajukan kepada peneliti yang mengundang Anda.",
      "There are no known risks and no company data are requested. Because the form is anonymous, answers cannot be withdrawn once handed in. Questions can be put to the researcher who invited you.")),
    p([t("☐  ", { size: 22 }), t(L("Saya telah membaca penjelasan di atas dan setuju untuk berpartisipasi.", "I have read the information above and agree to take part."))], { after: 60 }),
  ];

  // ------------------------------------------------ page 2: summary (after the briefing)
  const wR = [4038, 1600, 2000, 2000];
  const rules = [
    [L("Indikator (berlaku)", "Indicator (applies)"), "Normal", L("Sedang", "Moderate"), L("Berat", "Severe")],
    [L("THI (umur ≥ 21 hari)", "THI (day 21 on)"), "< 26", "26–29", "> 29"],
    [L("|Suhu − T*| °C (umur < 21 hari), T* menurut bobot", "|T − T*| °C (before day 21), T* by weight"), "≤ 2", L("> 2 sampai 4", "> 2 to 4"), "> 4"],
    ["NH₃, ppm", "≤ 10", L("> 10 sampai 20", "> 10 to 20"), "> 20"],
    ["CO₂, ppm", L("≤ 3.000", "≤ 3,000"), L("> 3.000 sampai 3.500", "> 3,000 to 3,500"), L("> 3.500", "> 3,500")],
  ];
  const summary = [
    h(L("Ringkasan rancangan (untuk dibaca setelah presentasi)", "Summary of the design (to read after the presentation)")),
    ...SUMMARY.map((s) => bullet(s[k])),
    table(wR, rules.map((r, i) => new TableRow({ children: r.map((c, j) => cell(c, wR[j], { fill: i === 0 ? GREY : undefined, bold: i === 0, size: 17 })) }))),
  ];

  // ------------------------------------------------ Part A
  const wB = [480, 5240, 1100, 440, 440, 440, 440, 440, 518];
  const itemTable = (items, start) => table(wB, [
    new TableRow({ tableHeader: true, children: [hc("No", wB[0]), hc(L("Butir", "Item"), wB[1]), hc(L("Bidang", "Domain"), wB[2]),
      ...["1", "2", "3", "4", "5", "TD"].map((x, i) => hc(x, wB[3 + i], C))] }),
    ...items.map(([, dom, id, en], i) => new TableRow({ cantSplit: true, children: [
      cell(String(start + i), wB[0], { bold: true }), cell(L(id, en), wB[1], { size: 17 }), cell(FIELD[dom][k], wB[2], { size: 15, italics: true }),
      ...[0, 1, 2, 3, 4].map((j) => cell("", wB[3 + j], C)), cell("", wB[8], { ...C, fill: "F2F2F2" }),
    ] })),
  ]);
  const partB = [
    h(L("Bagian A — Penilaian rancangan (diisi setelah presentasi)", "Part A — Rate the design (after the presentation)"), { pageBreak: true }),
    p(t(L("Beri tanda ✓ pada satu kolom per baris (1–5 atau TD). Pilih TD (tidak dapat menilai) bila butir itu di luar bidang Anda; kolom Bidang menunjukkan siapa yang paling dapat menilainya.",
      "Tick ✓ one column per row (1–5 or TD). Choose TD (cannot judge) when an item is outside your field; the Domain column shows who can best judge it."), { size: 17 })),
    p(t(L("A1. Seberapa sesuai aturan berikut?  1 = tidak sesuai, 2 = perlu revisi besar, 3 = perlu revisi sedang, 4 = sesuai dengan revisi kecil, 5 = sesuai tanpa revisi",
      "A1. How appropriate are these rules?  1 = not appropriate, 2 = needs major revision, 3 = needs moderate revision, 4 = appropriate with minor revision, 5 = appropriate as it is"), { size: 17, bold: true }), { after: 40 }),
    itemTable(RULE_ITEMS, 1),
    p(t(L("A2. Seberapa setuju Anda?  1 = sangat tidak setuju, 2 = tidak setuju, 3 = antara setuju dan tidak setuju, 4 = setuju, 5 = sangat setuju",
      "A2. How far do you agree?  1 = strongly disagree, 2 = disagree, 3 = neither agree nor disagree, 4 = agree, 5 = strongly agree"), { size: 17, bold: true }), { after: 40, keepNext: true }),
    itemTable(AGREE_ITEMS, RULE_ITEMS.length + 1),
  ];

  // ------------------------------------------------ Part B
  const fmt = (s) => L(`Minggu ${s.week}; ${s.weight_g.toLocaleString("en-US")} g; ${s.T_C.toFixed(1)} °C; RH ${s.RH_pct.toFixed(1)}%; angin ${s.air_speed_ms.toFixed(2)} m/s; CO₂ ${s.CO2_ppm} ppm; NH₃ ${s.NH3_ppm.toFixed(1)} ppm`,
    `Week ${s.week}; ${s.weight_g.toLocaleString("en-US")} g; ${s.T_C.toFixed(1)} °C; RH ${s.RH_pct.toFixed(1)}%; air ${s.air_speed_ms.toFixed(2)} m/s; CO₂ ${s.CO2_ppm} ppm; NH₃ ${s.NH3_ppm.toFixed(1)} ppm`);
  const wC = [450, 2150, 2400, 5770, 1250, 1250, 1300];
  const scale = "1  2  3  4  5";
  const rowsC = [new TableRow({ tableHeader: true, children: [
    hc("No", wC[0]), hc(L("Kondisi zona", "Zone condition"), wC[1]), hc(L("Tingkat dan penyebab dari sistem", "Level and cause from the system"), wC[2]),
    hc(L("Tugas dari sistem, berurutan (sumber)", "Tasks from the system, in order (source)"), wC[3]),
    hc(L("(a) Tingkat tepat untuk kondisi ini? 1–5", "(a) Level right for this condition? 1–5"), wC[4]),
    hc(L("(b) Kemungkinan penyebab masuk akal? 1–5", "(b) Possible cause plausible? 1–5"), wC[5]),
    hc(L("(c) Layak sebagai langkah pertama? 1–5", "(c) Acceptable as first steps? 1–5"), wC[6]),
  ] })];
  CASE_IDS.forEach((id, n) => {
    const x = shown[id];
    let levelCell, taskCell, b, c;
    if (!x) {
      levelCell = [p(t("Normal", { size: 16, bold: true }), { after: 0 })];
      taskCell = L("– (tidak ada tugas pada tingkat Normal)", "– (no tasks at Normal)");
      b = "–"; c = "–";
    } else {
      const cause = x.cause.split("+").map((cc) => (CAUSE[cc] ? CAUSE[cc][k] : cc)).join(" + ");
      const kind = x.thermal_kind && KIND[x.thermal_kind] ? ` (${KIND[x.thermal_kind][k]})` : "";
      levelCell = [p([t(LEVEL[x.level][k], { size: 16, bold: true }), t(` (${MODE[x.task_mode][k]})`, { size: 14, italics: true })], { after: 0 }),
        p(t(cause + kind, { size: 15 }), { after: 10 }),
        p([t(L("Kemungkinan penyebab: ", "Possible cause: "), { size: 14 }), t(x.possible_cause ? (lang === "id" ? PCAUSE_ID[x.possible_cause] : x.possible_cause_text) : "–", { size: 15, bold: true })], { after: 0 })];
      taskCell = x.tasks.map((tk, i) => p([t(`${i + 1}. ${lang === "id" ? TASK_ID[tk.code] : tk.text}`, { size: 16 }),
        t(`  [${tk.basis === "I" ? L("inferensi perancang, tanpa sumber", "designers' inference, no source") : tk.source}]`, { size: 14 })], { after: 15 }));
      for (const note of x.notes) taskCell.push(p(t(L("Catatan: ", "Note: ") + note, { size: 14, italics: true }), { after: 0 }));
      b = scale; c = scale;
    }
    rowsC.push(new TableRow({ cantSplit: true, children: [
      cell(String(n + 1), wC[0], { bold: true }), cell(fmt(scen[id]), wC[1], { size: 15 }), cell(levelCell, wC[2]), cell(taskCell, wC[3], { size: 15 }),
      cell(scale, wC[4], C), cell(b, wC[5], C), cell(c, wC[6], C),
    ] }));
  });
  const partC = [
    h(L("Bagian B — Penilaian kondisi dan tugas", "Part B — Rate the conditions and tasks")),
    p(t(L(`Sembilan kondisi zona nyata dari dataset terbuka (Brasil), dengan tingkat, kemungkinan penyebab dan tugas yang diberikan sistem. Nilailah (a) apakah tingkatnya tepat untuk kondisi itu, (b) apakah kemungkinan penyebabnya masuk akal, dan (c) apakah urutan tugasnya layak sebagai langkah pertama. 1 = sama sekali tidak, 5 = sepenuhnya. Untuk kondisi Normal hanya (a). Lingkari satu angka per kolom. Terima kasih.`,
      `Nine real zone conditions from an open dataset (Brazil), with the level, possible cause and tasks the system gives. Rate (a) whether the level is right for the condition, (b) whether the possible cause is plausible, and (c) whether the task list is acceptable as the first steps. 1 = not at all, 5 = fully. For Normal conditions, (a) only. Circle one number per column. Thank you.`), { size: 17 })),
    table(wC, rowsC),
  ];

  const numbering = { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 360, hanging: 240 } } } }] }] };
  const portrait = { page: { size: A4, margin: MARGIN } };
  const landscape = { page: { size: { ...A4, orientation: PageOrientation.LANDSCAPE }, margin: { ...MARGIN, top: 700, bottom: 700 } } };
  const styles = { default: { document: { run: { font: FONT, size: 20 } } } };
  return new Document({ styles, numbering, sections: [{ properties: portrait, children: [...before, ...summary, ...partB] },
    { properties: landscape, children: partC }] });
}

(async () => {
  fs.writeFileSync(path.join(__dirname, "Form_Expert_Rating_ID.docx"), await Packer.toBuffer(build("id")));
  fs.writeFileSync(path.join(__dirname, "Form_Expert_Rating_EN.docx"), await Packer.toBuffer(build("en")));
  const items = [...RULE_ITEMS, ...AGREE_ITEMS].map(([id, dom, idText, en], i) => ({ id, number: i + 1, block: id.startsWith("R") ? "A1" : "A2",
    domains: { ab: ["a", "b"], ad: ["a", "d"], ac: ["a", "c"], c: ["c"], all: ["a", "b", "c", "d"] }[dom], text_id: idText, text_en: en,
    negative: ["T5", "S5"].includes(id), attention_check: id === "CHK" }));
  fs.writeFileSync(path.join(__dirname, "form_spec.json"), JSON.stringify({ items, cases: cases(), dropped: DROPPED, normal_near: NORMAL_NEAR }, null, 1));
  console.log("form written (ID for the experts, EN translation) and form_spec.json");
})();
