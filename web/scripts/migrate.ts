import { openDb } from "../src/db";
const file = process.env.TRIAGEKIT_DB ?? "./data/app.db";
openDb(file).then(() => console.log(`migrated ${file}`));
