// Small pure helpers (easy to test, no React).

// Same rules the backend enforces (loader.py). The backend stays the authority; this only gives early hints.
export const GITHUB_RE = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+?(?:\.git)?\/?$/;
export const SAMPLE_RE = /^sample:[A-Za-z0-9_-]+$/;
export const ISSUE_MIN = 10;
export const ISSUE_MAX = 4000;

export function validateRepo(value) {
  const t = (value || "").trim();
  if (!t) return { ok: false, hint: "" };
  if (SAMPLE_RE.test(t) || GITHUB_RE.test(t)) return { ok: true, hint: "" };
  return { ok: false, hint: "Use https://github.com/<owner>/<repo> or sample:<name>" };
}

export function validateIssue(value) {
  const n = (value || "").trim().length;
  if (n === 0) return { ok: false, hint: "" };
  if (n < ISSUE_MIN) return { ok: false, hint: `Add a little more detail (at least ${ISSUE_MIN} characters).` };
  if (n > ISSUE_MAX) return { ok: false, hint: `Too long: ${ISSUE_MAX} characters maximum.` };
  return { ok: true, hint: "" };
}

export function repoLabel(ref) {
  if (!ref) return "";
  if (ref.startsWith("sample:")) return ref;
  return ref.replace(/^https:\/\/github\.com\//, "").replace(/\.git$/, "").replace(/\/$/, "");
}

export function totalSeconds(timings) {
  if (!timings) return null;
  const vals = Object.values(timings).filter((v) => typeof v === "number");
  return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) * 10) / 10 : null;
}

export const hasText = (v) => typeof v === "string" && v.trim().length > 0;

// Save `content` as a file in the browser. The Blob is built directly from the string, so the file
// holds exactly these characters (UTF-8, no BOM, line endings and trailing newline untouched).
// Returns false if the browser refused.
export function downloadTextFile(filename, content, mime = "text/x-python") {
  try {
    const blob = new Blob([content], { type: `${mime};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return true;
  } catch {
    return false;
  }
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

// Parse a unified diff (as produced by the backend with difflib) into display rows with line numbers.
export function parseDiff(text) {
  const rows = [];
  if (!text) return rows;
  let oldNo = 0, newNo = 0, oldLeft = 0, newLeft = 0;
  for (const line of text.split("\n")) {
    const inHunk = oldLeft > 0 || newLeft > 0;
    if (!inHunk && (line.startsWith("--- ") || line.startsWith("+++ "))) {
      rows.push({ type: "file", text: line });
    } else if (!inHunk && line.startsWith("@@")) {
      const m = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(line);
      if (m) {
        oldNo = +m[1]; oldLeft = m[2] === undefined ? 1 : +m[2];
        newNo = +m[3]; newLeft = m[4] === undefined ? 1 : +m[4];
      }
      rows.push({ type: "hunk", text: line });
    } else if (line.startsWith("+")) {
      rows.push({ type: "add", text: line.slice(1), newNo: newNo++ });
      newLeft--;
    } else if (line.startsWith("-")) {
      rows.push({ type: "del", text: line.slice(1), oldNo: oldNo++ });
      oldLeft--;
    } else if (inHunk) {
      rows.push({ type: "ctx", text: line.slice(1), oldNo: oldNo++, newNo: newNo++ });
      oldLeft--; newLeft--;
    } else if (line !== "") {
      rows.push({ type: "ctx", text: line });
    }
  }
  return rows;
}
