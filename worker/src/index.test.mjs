import { test } from "node:test";
import assert from "node:assert/strict";
import { isPageView, maskIp, device, formatMessage } from "./index.js";

const req = (headers = {}, extra = {}) =>
  Object.assign(new Request("https://faqihhakim.tech/projects", { headers }), extra);
const ok = new Response("x", { status: 200 });
const CHROME = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/129 Mobile Safari/537.36";

test("page view only for human html documents", () => {
  assert.equal(isPageView(req({ "sec-fetch-dest": "document", "user-agent": CHROME }), ok), true);
  assert.equal(isPageView(req({ "sec-fetch-dest": "image", "user-agent": CHROME }), ok), false);
  assert.equal(isPageView(req({ accept: "text/html", "user-agent": "Googlebot/2.1" }), ok), false);
  assert.equal(isPageView(req({ accept: "text/html", "user-agent": "LinkedInBot/1.0" }), ok), false);
  assert.equal(isPageView(req({ "sec-fetch-dest": "document", "user-agent": CHROME }),
    new Response(null, { status: 301 })), false);
});

test("ip is masked", () => {
  assert.equal(maskIp("182.253.12.44"), "182.253.12.xxx");
  assert.equal(maskIp("2001:db8:abcd:12::1"), "2001:db8:abcd:xxxx");
  assert.equal(maskIp(null), "?");
});

test("device detection", () => {
  assert.equal(device(CHROME), "Chrome, Android");
});

test("message has location, org, referrer and masked ip", () => {
  const r = req({ "user-agent": CHROME, referer: "https://www.linkedin.com/in/x", "cf-connecting-ip": "1.2.3.4" });
  Object.defineProperty(r, "cf", { value: { city: "Jakarta", country: "ID", asn: 7713, asOrganization: "Telkom" } });
  const msg = formatMessage(r, new Date("2026-10-06T10:00:00Z"));
  assert.match(msg, /Lokasi: Jakarta, ID/);
  assert.match(msg, /AS7713 Telkom/);
  assert.match(msg, /Dari: www.linkedin.com/);
  assert.match(msg, /IP: 1.2.3.xxx/);
  assert.doesNotMatch(msg, /1\.2\.3\.4/);
});
