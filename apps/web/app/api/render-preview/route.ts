import { spawn } from "node:child_process";
import path from "node:path";

import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

type ContentModuleRecord = {
  module_type?: string;
  heading?: string;
};

async function renderWithSharedRenderer(payload: {
  draft_markdown: string;
  post_type: string;
  content_modules: ContentModuleRecord[];
}): Promise<string> {
  const rendererPath = path.resolve(process.cwd(), "..", "..", "scripts", "article-html-renderer.js");
  // Read payload from stdin to avoid ENAMETOOLONG on large HTML articles.
  const runner = [
    "const rendererPath = process.argv[1];",
    "let data = '';",
    "process.stdin.setEncoding('utf8');",
    "process.stdin.on('data', chunk => { data += chunk; });",
    "process.stdin.on('end', () => {",
    "  const payload = JSON.parse(data);",
    "  const { renderArticleHtml } = require(rendererPath);",
    "  const html = renderArticleHtml(payload.draft_markdown, {",
    "    post_type: payload.post_type,",
    "    content_modules: payload.content_modules,",
    "  });",
    "  process.stdout.write(JSON.stringify({ html }));",
    "});",
  ].join("\n");

  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ["-e", runner, rendererPath], {
      cwd: process.cwd(),
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });

    const timer = setTimeout(() => {
      child.kill();
      reject(new Error("Preview render timed out."));
    }, 15000);

    child.on("close", (code) => {
      clearTimeout(timer);
      if (stderr.trim()) { reject(new Error(stderr.trim())); return; }
      if (code !== 0) { reject(new Error(`Renderer exited with code ${code}.`)); return; }
      const parsed = JSON.parse(stdout || "{}") as { html?: string };
      resolve(String(parsed.html || ""));
    });

    child.on("error", (err) => { clearTimeout(timer); reject(err); });

    child.stdin.write(JSON.stringify(payload), "utf8");
    child.stdin.end();
  });
}

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json() as {
      draft_markdown?: string;
      post_type?: string;
      content_modules?: ContentModuleRecord[];
    };

    const draftMarkdown = String(payload.draft_markdown || "").trim();
    if (!draftMarkdown) {
      return NextResponse.json({ error: "Draft content is required." }, { status: 400 });
    }

    const html = await renderWithSharedRenderer({
      draft_markdown: draftMarkdown,
      post_type: String(payload.post_type || "informational_blog"),
      content_modules: Array.isArray(payload.content_modules) ? payload.content_modules : [],
    });

    return NextResponse.json({ html });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Preview render failed." },
      { status: 500 },
    );
  }
}
