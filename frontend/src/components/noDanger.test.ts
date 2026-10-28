import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

describe("FE-LNT-01 no raw HTML sinks", () => {
  it("ESLint reports react/no-danger on dangerouslySetInnerHTML", async () => {
    const eslint = new ESLint({ cwd: join(SRC, "..") });
    const [res] = await eslint.lintText(
      'export const A = ({h}:{h:string}) => <div dangerouslySetInnerHTML={{ __html: h }} />;\n',
      { filePath: join(SRC, "components", "Probe.tsx") },
    );
    expect(res.messages.map((m) => m.ruleId)).toContain("react/no-danger");
    expect(res.messages.find((m) => m.ruleId === "react/no-danger")?.severity).toBe(2);
  });

  it("no source file uses dangerouslySetInnerHTML", () => {
    const needle = ["dangerously", "SetInnerHTML"].join("");
    const hits = walk(SRC)
      .filter((f) => /\.(ts|tsx)$/.test(f))
      .filter((f) => !f.endsWith("noDanger.test.ts"))
      .filter((f) => readFileSync(f, "utf8").includes(needle));
    expect(hits).toEqual([]);
  });
});
