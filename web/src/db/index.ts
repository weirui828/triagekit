import { createClient } from "@libsql/client";
import { drizzle, type LibSQLDatabase } from "drizzle-orm/libsql";
import { migrate } from "drizzle-orm/libsql/migrator";
import { mkdirSync } from "node:fs";
import path from "node:path";
import * as schema from "./schema";

export type Db = LibSQLDatabase<typeof schema>;

export async function openDb(file = process.env.TRIAGEKIT_DB ?? "./data/app.db"): Promise<Db> {
  if (file !== ":memory:") mkdirSync(path.dirname(file), { recursive: true });
  const client = createClient({ url: file === ":memory:" ? ":memory:" : `file:${file}` });
  await client.execute("PRAGMA journal_mode = WAL");
  await client.execute("PRAGMA foreign_keys = ON");
  const db = drizzle(client, { schema });
  await migrate(db, { migrationsFolder: path.join(process.cwd(), "drizzle") });
  return db;
}

const g = globalThis as unknown as { __triagekitDb?: Promise<Db> };
export function db(): Promise<Db> {
  if (!g.__triagekitDb) g.__triagekitDb = openDb();
  return g.__triagekitDb;
}
