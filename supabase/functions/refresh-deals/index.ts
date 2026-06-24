// Supabase Edge Function: refresh-deals
// Pulls today's NSE bulk + block deal CSVs (static CDN — reachable from datacenter
// IPs, unlike NSE's JS-gated JSON APIs) and upserts into market_deals with a
// per-date reload (delete the date, re-insert) so re-runs are idempotent.
// Writes with the service role (injected via env); RLS otherwise blocks writes.
// Deployed via the Supabase MCP. verify_jwt=false so the dashboard can call it.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";
import { parse } from "jsr:@std/csv@1/parse";

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};
const MONTHS: Record<string, string> = {
  JAN: "01", FEB: "02", MAR: "03", APR: "04", MAY: "05", JUN: "06",
  JUL: "07", AUG: "08", SEP: "09", OCT: "10", NOV: "11", DEC: "12",
};

function toISO(d?: string): string | null {
  const m = (d ?? "").trim().match(/^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/);
  if (!m) return null;
  const mm = MONTHS[m[2].toUpperCase()];
  return mm ? `${m[3]}-${mm}-${m[1].padStart(2, "0")}` : null;
}
function num(v?: string): number | null {
  if (!v) return null;
  const x = parseFloat(String(v).replaceAll(",", ""));
  return Number.isFinite(x) ? x : null;
}

async function fetchKind(url: string, kind: string) {
  const r = await fetch(url, { headers: { "User-Agent": UA, "Accept": "*/*" } });
  if (!r.ok) return [];
  const text = await r.text();
  let recs: Record<string, string>[] = [];
  try {
    recs = parse(text, { skipFirstRow: true }) as Record<string, string>[];
  } catch {
    return [];
  }
  const out: Record<string, unknown>[] = [];
  for (const rec of recs) {
    const deal_date = toISO(rec["Date"]);
    const symbol = (rec["Symbol"] ?? "").trim();
    const side = (rec["Buy/Sell"] ?? "").trim().toUpperCase();
    if (!deal_date || !symbol || !side) continue;
    const qty = num(rec["Quantity Traded"]);
    const price = num(rec["Trade Price / Wght. Avg. Price"]);
    out.push({
      deal_date, symbol, security: rec["Security Name"] ?? null,
      client: (rec["Client Name"] ?? "").trim(), side, qty, price,
      value: qty && price ? qty * price : null, kind,
    });
  }
  return out;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    const supa = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );
    const bulk = await fetchKind("https://nsearchives.nseindia.com/content/equities/bulk.csv", "bulk");
    const block = await fetchKind("https://nsearchives.nseindia.com/content/equities/block.csv", "block");
    const rows = [...bulk, ...block];
    const dates = [...new Set(rows.map((r) => r.deal_date))];
    for (const d of dates) {
      const { error } = await supa.from("market_deals").delete().eq("deal_date", d);
      if (error) throw error;
    }
    if (rows.length) {
      const { error } = await supa.from("market_deals").insert(rows);
      if (error) throw error;
    }
    return new Response(
      JSON.stringify({ ok: true, inserted: rows.length, bulk: bulk.length, block: block.length, dates }),
      { headers: { ...CORS, "Content-Type": "application/json" } },
    );
  } catch (e) {
    return new Response(JSON.stringify({ ok: false, error: String(e) }), {
      status: 500,
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
});
