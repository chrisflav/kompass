import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";
import { brotliCompress, constants, gzip } from "node:zlib";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const brotli = promisify(brotliCompress);
const gz = promisify(gzip);

/** What is worth compressing: text, and KaTeX's uncompressed .ttf fallbacks.
 *  woff2/woff and images already are compressed. */
const COMPRESSIBLE = /\.(js|css|html|svg|json|ttf)$/;

/**
 * Write a `.gz` and a `.br` next to every compressible file of the build, at
 * the highest levels, so the web server can hand them out as they are
 * (nginx's `gzip_static`) instead of compressing on every request at the low
 * level it can afford there. A variant that would not be smaller is skipped,
 * and the server then falls back to the original.
 */
function precompress(): Plugin {
  let outDir = "dist";
  return {
    name: "kompass-precompress",
    apply: "build",
    configResolved(config) {
      outDir = config.build.outDir;
    },
    async writeBundle() {
      const entries = await readdir(outDir, { recursive: true, withFileTypes: true });
      const files = entries
        .filter((entry) => entry.isFile() && COMPRESSIBLE.test(entry.name))
        .map((entry) => join(entry.parentPath, entry.name));
      await Promise.all(
        files.map(async (file) => {
          const source = await readFile(file);
          const variants: [string, Buffer][] = [
            [".gz", await gz(source, { level: 9 })],
            [
              ".br",
              await brotli(source, {
                params: {
                  [constants.BROTLI_PARAM_QUALITY]: constants.BROTLI_MAX_QUALITY,
                  [constants.BROTLI_PARAM_SIZE_HINT]: source.length,
                },
              }),
            ],
          ];
          for (const [suffix, compressed] of variants) {
            if (compressed.length < source.length) await writeFile(file + suffix, compressed);
          }
        }),
      );
    },
  };
}

export default defineConfig({
  plugins: [react(), precompress()],
  server: { port: 5173 },
});
