// Supabase Edge Function: refresh-buybacks
// Discovers current tender buybacks by probing chittorgarh ids upward from the stored
// frontier (gap-stop), regex-parsing each page (no pandas needed — all fields are in the
// text), pricing via Yahoo, and upserting the buyback master. The richer acceptance/exp
// scoring stays in the Python `scanner.run buyback_arb --save`; this just keeps the master
// list current from the UI. chittorgarh + Yahoo both serve datacenter IPs (probed).
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};
const MONTHS: Record<string, string> = {
  January: "01", February: "02", March: "03", April: "04", May: "05", June: "06",
  July: "07", August: "08", September: "09", October: "10", November: "11", December: "12",
};

function dateISO(s?: string | null): string | null {
  if (!s) return null;
  const m = s.match(/([A-Za-z]+) ([0-9]{1,2}), ([0-9]{4})/);
  if (!m) return null;
  const mm = MONTHS[m[1]];
  return mm ? `${m[3]}-${mm}-${m[2].padStart(2, "0")}` : null;
}
function numf(s?: string | null): number | null {
  if (!s) return null;
  const x = parseFloat(String(s).replaceAll(",", ""));
  return Number.isFinite(x) ? x : null;
}
function arbFloor(entry: number, buyback: number, accFrac: number): number | null {
  const cap = 200000, costBps = 30;
  const n = Math.floor(cap / entry);
  if (n <= 0) return null;
  const accepted = n * accFrac, resid = n - accepted;
  const buyCost = n * entry * (1 + costBps / 1e4);
  const proceeds = accepted * buyback + resid * entry * (1 - costBps / 1e4); // residual flat
  return proceeds / buyCost - 1;
}

async function fetchPage(bid: number): Promise<string | null> {
  const r = await fetch(`https://www.chittorgarh.com/buyback/x/${bid}/`, { headers: { "User-Agent": UA } });
  if (r.status !== 200) return null;
  const t = await r.text();
  return t.includes("Buyback") ? t : null;
}

function parseBuyback(html: string, bid: number) {
  const text = html.replace(/<[^>]*>/g, " ").replace(/&#?[a-z0-9]+;/gi, " ").replace(/\s+/g, " ");
  const ent = text.match(/([0-9]+) Equity Shares out of every ([0-9]+)/i);
  if (!ent) return null; // not a tender offer
  const clean = html.split(String.fromCharCode(92)).join("");
  const symM = clean.match(/"nse(?:Code|_symbol)":"([A-Z0-9&.-]{2,})"/);
  const bpM = text.match(/buyback price of[^0-9]*([0-9,]+)/i);
  const rdM = text.match(/record date[^.]*is ([A-Za-z]+ [0-9]{1,2}, [0-9]{4})/i);
  const cdM = text.match(/Buyback Closing Date ([A-Za-z]+ [0-9]{1,2}, [0-9]{4})/i);
  const isM = text.match(/Issue Size [(]Amount[)][^0-9]*([0-9,]+(?:[.][0-9]+)?) Crore/i);
  const titleM = html.match(/<title>([^<]*)/);
  return {
    chittorgarh_id: bid,
    company: titleM ? titleM[1].replace("Buyback Detail", "").trim() : null,
    symbol: symM ? symM[1] : null,
    buyback_price: bpM ? numf(bpM[1]) : null,
    record_date: rdM ? dateISO(rdM[1]) : null,
    close_date: cdM ? dateISO(cdM[1]) : null,
    entitlement_small: parseInt(ent[1]) / parseInt(ent[2]),
    issue_size_cr: isM ? numf(isM[1]) : null,
  };
}

async function yahooPrice(sym: string): Promise<number | null> {
  try {
    const r = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${sym}.NS?range=5d&interval=1d`,
      { headers: { "User-Agent": UA } },
    );
    const j = await r.json();
    return j?.chart?.result?.[0]?.meta?.regularMarketPrice ?? null;
  } catch {
    return null;
  }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  try {
    const supa = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const { data: maxRow } = await supa.from("buybacks").select("chittorgarh_id")
      .order("chittorgarh_id", { ascending: false }).limit(1);
    let bid = Math.max((maxRow?.[0]?.chittorgarh_id ?? 210) - 3, 200);
    const today = new Date().toISOString().slice(0, 10);
    const rows: Record<string, unknown>[] = [];
    let gap = 0, fetched = 0;
    while (gap < 8 && fetched < 60) {
      const html = await fetchPage(bid);
      fetched++;
      await new Promise((r) => setTimeout(r, 150));
      if (!html) { gap++; bid++; continue; }
      gap = 0;
      const bb = parseBuyback(html, bid);
      bid++;
      if (!bb || !bb.symbol || !bb.buyback_price || !bb.entitlement_small) continue;
      const price = await yahooPrice(bb.symbol as string);
      let est_return: number | null = null;
      if (price && price > 0) {
        const premium = (bb.buyback_price as number) / price - 1;
        if (premium < -0.5 || premium > 1.5) continue; // implausible -> stale price
        est_return = arbFloor(price, bb.buyback_price as number, bb.entitlement_small as number);
      }
      const status = bb.close_date && (bb.close_date as string) >= today ? "open" : "settled";
      rows.push({ ...bb, est_return, status });
    }
    if (rows.length) {
      const { error } = await supa.from("buybacks").upsert(rows, { onConflict: "chittorgarh_id" });
      if (error) throw error;
    }
    return new Response(
      JSON.stringify({ ok: true, upserted: rows.length, scanned: fetched, found: rows.map((r) => r.symbol) }),
      { headers: { ...CORS, "Content-Type": "application/json" } },
    );
  } catch (e) {
    return new Response(JSON.stringify({ ok: false, error: String(e) }), {
      status: 500,
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
});
