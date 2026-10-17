// Copies the newest recorded video from test-results/ to ../demo/video/demo.webm (git-ignored).
import { copyFileSync, mkdirSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const results = path.resolve(here, "../test-results");

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(full);
    else if (entry.name.endsWith(".webm")) yield full;
  }
}

const videos = [...walk(results)].sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
if (videos.length === 0) {
  console.error(`No .webm file under ${results}. Did the Playwright run record a video?`);
  process.exit(1);
}
const target = path.resolve(here, "../../demo/video/demo.webm");
mkdirSync(path.dirname(target), { recursive: true });
copyFileSync(videos[0], target);
console.log(`Video: ${target} (${(statSync(target).size / 1e6).toFixed(1)} MB)`);
