/**
 * esbuild bundler for the CapsuleMemory widget.
 *
 * Usage:
 *   node build.js          # one-shot production build
 *   node build.js --watch  # rebuild on file changes
 *
 * Output: dist/widget.js  (self-contained IIFE, no external dependencies)
 */
const esbuild = require("esbuild");
const path = require("path");
const fs = require("fs");

const ENTRY = path.resolve(__dirname, "index.js");
const OUTFILE = path.resolve(__dirname, "dist", "widget.js");
const CSS_FILE = path.resolve(__dirname, "styles.css");
const isWatch = process.argv.includes("--watch");

/** Inline the CSS file as a string constant so the widget is fully self-contained. */
const cssInlinePlugin = {
  name: "css-inline",
  setup(build) {
    build.onResolve({ filter: /^\.\/styles\.css$/ }, (args) => ({
      path: CSS_FILE,
      namespace: "css-inline",
    }));

    build.onLoad({ filter: /.*/, namespace: "css-inline" }, (args) => {
      const css = fs.readFileSync(args.path, "utf8");
      return {
        contents: `export default ${JSON.stringify(css)};`,
        loader: "js",
      };
    });
  },
};

/** @type {import('esbuild').BuildOptions} */
const buildOptions = {
  entryPoints: [ENTRY],
  outfile: OUTFILE,
  bundle: true,
  minify: !isWatch,
  sourcemap: isWatch ? "inline" : false,
  format: "iife",
  globalName: "CapsuleMemoryWidget",
  target: ["es2020"],
  plugins: [cssInlinePlugin],
  logLevel: "info",
};

async function main() {
  if (isWatch) {
    const ctx = await esbuild.context(buildOptions);
    await ctx.watch();
    console.log("[capsule-widget] watching for changes...");
  } else {
    await esbuild.build(buildOptions);
    console.log(`[capsule-widget] built → ${OUTFILE}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
