import { readFileSync } from "node:fs";
import deckyPlugin from "@decky/rollup";
const { version } = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf8"),
);
export default deckyPlugin({
  plugins: [
    {
      name: "frontend-version",
      transform(code, id) {
        if (!id.endsWith("/src/deckyInstaller.ts")) return null;
        return {
          code: code.replace(
            '"__DDU_FRONTEND_VERSION__"',
            JSON.stringify(version),
          ),
          map: null,
        };
      },
    },
  ],
});
