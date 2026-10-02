import { NextResponse } from "next/server";
import { jsonBody, route } from "@/lib/http";
import { ml } from "@/lib/ml";
import { parseYamlOrJson } from "@/lib/yaml";
// Parses YAML/JSON text in Next.js, then validates through the canonical Python contract validator.
export const POST = route(async (req) => {
  const { text } = await jsonBody<{ text: string }>(req);
  let obj: unknown;
  try { obj = parseYamlOrJson(text); } catch (e) { return NextResponse.json({ ok: false, errors: [String(e)] }); }
  const v = await ml("post", "/contract/validate", { body: obj as Record<string, never> });
  return NextResponse.json({ ok: v.ok, errors: v.errors, contract: v.contract, contract_hash: v.contract_hash });
});
