// Runs refresh-buybacks' pure parser (TS -> JS by stripping the few type annotations) on a
// fixture and prints JSON. Driven by tests/test_edge_functions.py for Python/TS parity.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const pick = (a, b) => src.slice(src.indexOf(a), src.indexOf(b));
const code = (pick("const MONTHS", "function arbFloor") + pick("function parseBuyback", "async function yahooPrice"))
  .replace(/: Record<string, string>/, "")
  .replace(/\(s\?: string \| null\): (string|number) \| null/g, "(s)")
  .replace(/\(html: string, bid: number\)/, "(html, bid)");
const parseBuyback = new Function(code + "; return parseBuyback;")();
const html = fs.readFileSync(process.argv[3], "utf8");
console.log(JSON.stringify(parseBuyback(html, Number(process.argv[4]))));
