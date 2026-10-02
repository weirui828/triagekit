"use client";
export function Msg({ error, info }: { error?: string | null; info?: string | null }) {
  if (error) return <p className="err">{error}</p>;
  if (info) return <p className="info">{info}</p>;
  return null;
}
