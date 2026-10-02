import { parse } from "yaml";
export function parseYamlOrJson(text: string): unknown {
  const t = text.trim();
  if (t.startsWith("{")) return JSON.parse(t);
  return parse(t);
}
