import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { gzip } from "node:zlib";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const gz = promisify(gzip);

/** The text assets worth compressing; fonts and images already are. */
const COMPRESSIBLE = /\.(js|css|html|svg|json)$/;

/**
 * Write a `.gz` next to every text file of the build, at the highest level, so
 * the web server can hand it out as it is (nginx's `gzip_static`) instead of
 * compressing on every request at the low level it can afford there. Where it
 * would not be smaller it is skipped, and the server falls back to the original.
 * No `.br`: the SPA image's nginx has no brotli module to serve one.
 */
function precompress(): Plugin {
  let outDir = "dist";
  return {
    name: "kompass-precompress",
    apply: "build",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    async writeBundle() {
      const entries = await readdir(outDir, { recursive: true, withFileTypes: true });
      const files = entries
        .filter((entry) => entry.isFile() && COMPRESSIBLE.test(entry.name))
        .map((entry) => join(entry.parentPath, entry.name));
      await Promise.all(
        files.map(async (file) => {
          const source = await readFile(file);
          const compressed = await gz(source, { level: 9 });
          if (compressed.length < source.length) await writeFile(`${file}.gz`, compressed);
        }),
      );
    },
  };
}

export default defineConfig({
  plugins: [react(), precompress()],
  server: { port: 5173 },
});
