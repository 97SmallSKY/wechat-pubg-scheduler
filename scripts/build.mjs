import {mkdir, readFile, writeFile, copyFile} from "node:fs/promises";

const files = {
  "/": ["text/html; charset=utf-8", "index.html"],
  "/style.css": ["text/css; charset=utf-8", "style.css"],
  "/app.js": ["text/javascript; charset=utf-8", "app.js"],
};
const assets = {};
for (const [path, [type, file]] of Object.entries(files)) {
  assets[path] = [type, await readFile(new URL("../ui/" + file, import.meta.url), "utf8")];
}
await mkdir("dist/server", {recursive: true});
await mkdir("dist/.openai", {recursive: true});
await writeFile("dist/server/index.js",
  "const assets = " + JSON.stringify(assets) + ";\n" + await readFile("worker/index.mjs", "utf8") +
  "\nexport default {fetch(request, env) { return handler(request, env, undefined, assets); }};\n");
await copyFile(".openai/hosting.json", "dist/.openai/hosting.json");
