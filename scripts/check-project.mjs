import fs from "node:fs";

const required = [
  "package.json",
  "vite.config.ts",
  "src/main.tsx",
  "supabase/migrations/001_schema.sql",
  "supabase/migrations/002_seed_strategy.sql",
  ".github/workflows/deploy-pages.yml",
];

let failed = false;

for (const file of required) {
  if (!fs.existsSync(file)) {
    console.error(`Missing: ${file}`);
    failed = true;
  } else {
    console.log(`OK: ${file}`);
  }
}

if (failed) process.exit(1);
console.log("Project structure is ready.");
