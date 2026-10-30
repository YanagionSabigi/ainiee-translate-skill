// Same trusted offline KaTeX distribution/options as the browser. No npm required.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const context = { module: { exports: {} } };
context.exports = context.module.exports;
try {
  vm.runInNewContext(
    fs.readFileSync(
      path.join(__dirname, "../vendor/katex/katex.min.js"),
      "utf8",
    ),
    context,
    { timeout: 5000 },
  );
  const texts = JSON.parse(fs.readFileSync(0, "utf8"));
  for (const text of texts)
    context.module.exports.renderToString(text, {
      throwOnError: true,
      trust: false,
      strict: "error",
      maxExpand: 1000,
      maxSize: 20,
      macros: {},
    });
  process.stdout.write(JSON.stringify({ valid: true }));
} catch (error) {
  process.stdout.write(JSON.stringify({ error: String(error.message) }));
  process.exitCode = 1;
}
