// Builds docs/FINAL_REPORT.docx from docs/FINAL_REPORT.md.
// Usage: NODE_PATH=<dir with node_modules/docx> node docs/build_report_docx.js [input.md] [output.docx]
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageNumber, TableOfContents, PageBreak, TabStopType, VerticalAlign,
} = require("docx");

const MD = path.resolve(process.argv[2] || path.join(__dirname, "FINAL_REPORT.md"));
const OUT = path.resolve(process.argv[3] || path.join(__dirname, "FINAL_REPORT.docx"));

const FONT = "Calibri";
const NAVY = "1F3864";
const ACCENT = "2E75B6";
const GREY = "595959";
const ZEBRA = "F2F5FA";
const LINE = "BFC7D5";
const PAGE_W = 12240, PAGE_H = 15840, MARGIN = 1260; // US Letter, 0.875in margins
const CONTENT_W = PAGE_W - 2 * MARGIN; // 9720 DXA

const TITLE = "Agentic Digital Twin for Shop-Floor Performance";
const SUBTITLE = "Final Project Report";
const AUTHOR = "Mostafizur Rahman";
const DATE = "November 17, 2026";

// ---------- inline markdown -> runs ----------
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(new TextRun({ text: tok.slice(2, -2), ...base, bold: true }));
    else if (tok.startsWith("*")) out.push(new TextRun({ text: tok.slice(1, -1), ...base, italics: true }));
    else out.push(new TextRun({ text: tok.slice(1, -1), ...base, font: "Consolas", size: (base.size || 21) - 2, color: "7B2D26" }));
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const plain = (t) => t.replace(/\*\*/g, "").replace(/`/g, "");

// ---------- markdown -> blocks ----------
const lines = fs.readFileSync(MD, "utf8").replace(/\r/g, "").split("\n");
const blocks = [];
let i = 0;
while (i < lines.length) {
  const ln = lines[i];
  if (ln.trim() === "") { i++; continue; }
  if (/^---+\s*$/.test(ln)) { blocks.push({ t: "hr" }); i++; continue; }
  let m;
  if ((m = ln.match(/^(#{1,4})\s+(.*)$/))) { blocks.push({ t: "h", level: m[1].length, text: m[2] }); i++; continue; }
  if (ln.startsWith("```")) {
    const code = []; i++;
    while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
    i++; blocks.push({ t: "code", lines: code }); continue;
  }
  if ((m = ln.match(/^!\[(.*?)\]\((.*?)\)\s*$/))) { blocks.push({ t: "img", caption: m[1], src: m[2] }); i++; continue; }
  if (ln.startsWith("|")) {
    const rows = [];
    while (i < lines.length && lines[i].startsWith("|")) { rows.push(lines[i]); i++; }
    const cells = (r) => r.replace(/^\||\|\s*$/g, "").split("|").map((c) => c.trim());
    const header = cells(rows[0]);
    const body = rows.slice(2).map(cells);
    blocks.push({ t: "table", header, body }); continue;
  }
  if (/^\s*-\s+/.test(ln)) {
    const items = [];
    while (i < lines.length && /^\s*-\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*-\s+/, ""));
    blocks.push({ t: "ul", items }); continue;
  }
  if (/^\d+\.\s+/.test(ln)) {
    const items = [];
    while (i < lines.length && /^\d+\.\s+/.test(lines[i])) items.push(lines[i++].replace(/^\d+\.\s+/, ""));
    blocks.push({ t: "ol", items }); continue;
  }
  const para = [ln.trim()]; i++;
  while (i < lines.length && lines[i].trim() !== "" && !/^(#|\||```|!\[|\s*-\s|\d+\.\s|---)/.test(lines[i])) para.push(lines[i++].trim());
  blocks.push({ t: "p", text: para.join(" ") });
}

// numbered lists need their own numbering instance so each restarts at 1
let olCount = 0;
blocks.forEach((b) => { if (b.t === "ol") b.ref = `ol-${olCount++}`; });
const olConfigs = Array.from({ length: olCount }, (_, k) => ({
  reference: `ol-${k}`,
  levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 540, hanging: 300 } } } }],
}));

// ---------- builders ----------
const BORDER = { style: BorderStyle.SINGLE, size: 4, color: LINE };
const CELL_BORDERS = { top: BORDER, bottom: BORDER, left: BORDER, right: BORDER };

function buildTable({ header, body }) {
  const n = header.length;
  const all = [header, ...body];
  // proportional column widths from content length, with a floor, summing to CONTENT_W
  const weight = Array.from({ length: n }, (_, c) =>
    Math.max(11, Math.min(34, Math.max(...all.map((r) => plain(r[c] || "").length)))));
  const dense = n >= 6;
  const fs_ = dense ? 16 : n >= 4 ? 18 : 19; // half-points
  const total = weight.reduce((a, b) => a + b, 0);
  const widths = weight.map((w) => Math.floor((w / total) * CONTENT_W));
  widths[n - 1] += CONTENT_W - widths.reduce((a, b) => a + b, 0);
  const centered = Array.from({ length: n }, (_, c) =>
    c > 0 && all.slice(1).every((r) => plain(r[c] || "").length <= 28));

  const keepTogether = body.length <= 10;
  const mkCell = (txt, c, isHead, rowIdx) => new TableCell({
    width: { size: widths[c], type: WidthType.DXA },
    borders: CELL_BORDERS,
    verticalAlign: VerticalAlign.CENTER,
    shading: isHead
      ? { type: ShadingType.CLEAR, fill: NAVY, color: "auto" }
      : rowIdx % 2 === 1 ? { type: ShadingType.CLEAR, fill: ZEBRA, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({
      keepNext: keepTogether,
      alignment: isHead || centered[c] ? AlignmentType.CENTER : AlignmentType.LEFT,
      spacing: { before: 0, after: 0 },
      children: runs(txt, { font: FONT, size: fs_, bold: isHead || c === 0 && false, color: isHead ? "FFFFFF" : "262626" }),
    })],
  });

  const rows = [
    new TableRow({ tableHeader: true, cantSplit: true, children: header.map((h, c) => mkCell(h, c, true, 0)) }),
    ...body.map((r, ri) => new TableRow({ cantSplit: true, children: header.map((_, c) => mkCell(r[c] || "", c, false, ri)) })),
  ];
  return [
    new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths, rows }),
    new Paragraph({ spacing: { before: 0, after: 160 }, children: [] }),
  ];
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

function buildImage(b) {
  const file = path.resolve(path.dirname(MD), b.src);
  const { w, h } = pngSize(file);
  const width = 560; // px at 96 dpi, about 5.8in
  const height = Math.round((width * h) / w);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 60 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(file), transformation: { width, height },
        altText: { title: b.caption, description: b.caption, name: path.basename(file) } })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 0, after: 200 },
      children: runs(b.caption, { font: FONT, size: 18, italics: true, color: GREY }),
    }),
  ];
}

function buildCode(b) {
  const n = b.lines.length;
  return b.lines.map((l, k) => new Paragraph({
    spacing: { before: 0, after: 0, line: 250 },
    shading: { type: ShadingType.CLEAR, fill: "F4F4F4", color: "auto" },
    indent: { left: 200, right: 200 },
    border: {
      left: { style: BorderStyle.SINGLE, size: 18, color: ACCENT, space: 6 },
      ...(k === 0 ? { top: { style: BorderStyle.SINGLE, size: 4, color: "F4F4F4", space: 4 } } : {}),
      ...(k === n - 1 ? { bottom: { style: BorderStyle.SINGLE, size: 4, color: "F4F4F4", space: 4 } } : {}),
    },
    keepLines: true, keepNext: k < n - 1,
    children: [new TextRun({ text: l === "" ? " " : l, font: "Consolas", size: 17, color: "262626" })],
  })).concat([new Paragraph({ spacing: { before: 0, after: 120 }, children: [] })]);
}

// Section 1.. headings: md "##" -> Heading 1, "###" -> Heading 2. md "#" is the title (cover page).
const body = [];
let seenFirstH2 = false;
for (let bi = 0; bi < blocks.length; bi++) {
  const b = blocks[bi];
  const nextIsTable = blocks[bi + 1] && (blocks[bi + 1].t === "table" || blocks[bi + 1].t === "code");
  switch (b.t) {
    case "h":
      if (b.level === 1) break; // cover page
      if (b.level === 2) {
        // each top-level section starts a fresh page only when it is large; keep flow, avoid orphans
        body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(plain(b.text))] }));
        seenFirstH2 = true;
      } else if (b.level === 3) {
        body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(plain(b.text))] }));
      } else {
        body.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(plain(b.text))] }));
      }
      break;
    case "p": {
      const isNote = /^\*\*Results basis:/.test(b.text);
      body.push(new Paragraph({
        keepNext: nextIsTable, spacing: { before: 0, after: isNote ? 200 : 120, line: 276 },
        alignment: isNote ? AlignmentType.LEFT : AlignmentType.JUSTIFIED,
        ...(isNote ? {
          shading: { type: ShadingType.CLEAR, fill: "EAF1FB", color: "auto" },
          border: { left: { style: BorderStyle.SINGLE, size: 24, color: ACCENT, space: 8 } },
          indent: { left: 160, right: 160 },
        } : {}),
        children: runs(b.text, { font: FONT, size: 21 }),
      }));
      break;
    }
    case "ul":
      b.items.forEach((it) => body.push(new Paragraph({
        numbering: { reference: "bullets", level: 0 }, spacing: { before: 0, after: 60, line: 276 },
        children: runs(it, { font: FONT, size: 21 }),
      })));
      body.push(new Paragraph({ spacing: { before: 0, after: 60 }, children: [] }));
      break;
    case "ol":
      b.items.forEach((it) => body.push(new Paragraph({
        numbering: { reference: b.ref, level: 0 }, spacing: { before: 0, after: 60, line: 276 },
        children: runs(it, { font: FONT, size: 21 }),
      })));
      body.push(new Paragraph({ spacing: { before: 0, after: 60 }, children: [] }));
      break;
    case "table": body.push(...buildTable(b)); break;
    case "img": body.push(...buildImage(b)); break;
    case "code": body.push(...buildCode(b)); break;
    case "hr": break; // section headings already separate content
  }
}

// ---------- cover page ----------
const cover = [
  new Paragraph({ spacing: { before: 2600, after: 0 }, children: [] }),
  new Paragraph({
    spacing: { after: 160 },
    border: { top: { style: BorderStyle.SINGLE, size: 24, color: ACCENT, space: 14 } },
    children: [new TextRun({ text: SUBTITLE.toUpperCase(), font: FONT, size: 24, bold: true, color: ACCENT, characterSpacing: 60 })],
  }),
  new Paragraph({ spacing: { after: 240, line: 240 },
    children: [new TextRun({ text: TITLE, font: FONT, size: 60, bold: true, color: NAVY })] }),
  new Paragraph({ spacing: { after: 1400 },
    children: [new TextRun({ text: "A multi-agent LLM system that verifies fixes in a digital twin before recommending them to a human supervisor", font: FONT, size: 26, color: GREY })] }),
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Author", font: FONT, size: 18, bold: true, color: ACCENT, allCaps: true })] }),
  new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: AUTHOR, font: FONT, size: 24, color: "262626" })] }),
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Date", font: FONT, size: 18, bold: true, color: ACCENT, allCaps: true })] }),
  new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: DATE, font: FONT, size: 24, color: "262626" })] }),
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Evaluation basis", font: FONT, size: 18, bold: true, color: ACCENT, allCaps: true })] }),
  new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: "Real LLM run: gpt-4.1-mini, 10 seeds per cell, 6 systems, 5 scenarios", font: FONT, size: 24, color: "262626" })] }),
];

// ---------- contents page ----------
const toc = [
  new Paragraph({ spacing: { before: 0, after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 4 } }, children: [new TextRun({ text: "Contents", font: FONT, size: 34, bold: true, color: NAVY })] }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
  new Paragraph({ children: [new PageBreak()] }),
];

const headerFooter = {
  headers: { default: new Header({ children: [new Paragraph({
    spacing: { after: 0 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: LINE, space: 4 } },
    tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
    children: [
      new TextRun({ text: TITLE, font: FONT, size: 17, color: GREY }),
      new TextRun({ text: "\t" + SUBTITLE, font: FONT, size: 17, color: GREY }),
    ] })] }) },
  footers: { default: new Footer({ children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [
      new TextRun({ text: "Page ", font: FONT, size: 17, color: GREY }),
      new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 17, color: GREY }),
    ] })] }) },
};

const pageProps = { page: { size: { width: PAGE_W, height: PAGE_H }, margin: { top: 1300, bottom: 1200, left: MARGIN, right: MARGIN } } };

const doc = new Document({
  creator: AUTHOR,
  title: `${TITLE}: ${SUBTITLE}`,
  description: "Final project report with real-LLM evaluation results",
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 34, bold: true, color: NAVY },
        paragraph: { spacing: { before: 420, after: 160 }, keepNext: true, keepLines: true, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 26, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 300, after: 100 }, keepNext: true, keepLines: true, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 23, bold: true, color: NAVY },
        paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, keepLines: true, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
      ...olConfigs,
    ],
  },
  sections: [
    { properties: { page: { size: { width: PAGE_W, height: PAGE_H }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } }, children: cover },
    { properties: { ...pageProps, page: { ...pageProps.page, pageNumbers: { start: 1 } } }, ...headerFooter, children: [...toc, ...body] },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`wrote ${OUT} (${buf.length} bytes), ${blocks.length} blocks`);
});
