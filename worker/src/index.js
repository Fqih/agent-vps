// Pass every request through to the origin (Netlify) untouched, and in the
// background send one Telegram message per new human visitor per day.

const BOT_UA = /bot|crawl|spider|slurp|preview|monitor|uptime|curl|wget|python|go-http|headless|lighthouse|facebookexternalhit|whatsapp|telegram|discord|slack|vercel|netlify/i;
const DAY_SECONDS = 86400;

export default {
  async fetch(request, env, ctx) {
    const response = await fetch(request);
    if (isPageView(request, response)) {
      ctx.waitUntil(notify(request, env).catch((err) => console.error("notify failed", err)));
    }
    return response;
  },
};

export function isPageView(request, response) {
  if (request.method !== "GET" || response.status !== 200) return false;
  const dest = request.headers.get("sec-fetch-dest");
  const accept = request.headers.get("accept") || "";
  if (dest ? dest !== "document" : !accept.includes("text/html")) return false;
  return !BOT_UA.test(request.headers.get("user-agent") || "");
}

export function maskIp(ip) {
  if (!ip) return "?";
  if (ip.includes(".")) return ip.split(".").slice(0, 3).concat("xxx").join(".");
  return ip.split(":").slice(0, 3).join(":") + ":xxxx";
}

export function device(ua) {
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Windows/.test(ua) ? "Windows"
    : /Mac OS/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "?";
  const browser = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Chrome\//.test(ua) ? "Chrome"
    : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "?";
  return `${browser}, ${os}`;
}

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function formatMessage(request, now = new Date()) {
  const cf = request.cf || {};
  const url = new URL(request.url);
  const ref = request.headers.get("referer");
  const refHost = ref ? new URL(ref).hostname : "langsung / tidak diketahui";
  const place = [cf.city, cf.region, cf.country].filter(Boolean).join(", ") || "?";
  const time = now.toLocaleString("id-ID", { timeZone: "Asia/Jakarta", dateStyle: "medium", timeStyle: "short" });
  return [
    "Pengunjung portfolio",
    `Lokasi: ${place}`,
    `Jaringan: AS${cf.asn ?? "?"} ${cf.asOrganization ?? ""}`.trim(),
    `IP: ${maskIp(request.headers.get("cf-connecting-ip"))}`,
    `Dari: ${refHost === url.hostname ? "navigasi internal" : refHost}`,
    `Halaman: ${url.pathname}`,
    `Perangkat: ${device(request.headers.get("user-agent") || "")}`,
    `Waktu: ${time} WIB`,
  ].join("\n");
}

async function notify(request, env) {
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  const day = new Date().toISOString().slice(0, 10);
  const key = `v:${await sha256(`${ip}|${day}`)}`;
  if (await env.VISITS.get(key)) return;
  await env.VISITS.put(key, "1", { expirationTtl: DAY_SECONDS });

  const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      chat_id: env.TELEGRAM_CHAT_ID,
      text: formatMessage(request),
      disable_web_page_preview: true,
    }),
  });
  if (!res.ok) throw new Error(`telegram ${res.status}`);
}
