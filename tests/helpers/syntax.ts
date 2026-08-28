import { execFileSync } from "node:child_process";

export function assertJavaScriptSyntax(filePath: string, _preferredMode = "auto"): void {
  execFileSync("node", ["--check", filePath], {
    stdio: "pipe"
  });
}

export function assertPythonSyntax(filePaths: string[]): void {
  if (!filePaths.length) return;

  const script = [
    "import ast, sys, tokenize",
    "for path in sys.argv[1:]:",
    "    with tokenize.open(path) as fh:",
    "        source = fh.read()",
    "    ast.parse(source, filename=path)"
  ].join("\n");

  for (let offset = 0; offset < filePaths.length; offset += 40) {
    execFileSync("python", ["-c", script, ...filePaths.slice(offset, offset + 40)], {
      stdio: "pipe"
    });
  }
}
