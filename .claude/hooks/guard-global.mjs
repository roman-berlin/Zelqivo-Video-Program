#!/usr/bin/env node
/**
 * Roman's GLOBAL PreToolUse guard — the minimal, repo-agnostic half of the
 * "production always asks" contract, for repos that have no guard of their own.
 *
 * Installed by install.sh to ~/.claude/hooks/ (all local sessions) and seeded
 * by `install.sh --repo` into other repos' .claude/hooks/ (their cloud
 * sessions). Stock-Compass has its own, stricter guard; hooks from every
 * scope run, and the most restrictive decision wins.
 *
 * Scope ON PURPOSE: only SQL content on Supabase MCP calls. No project refs
 * (repo-specific), no git logic (permission rules + GitHub branch protection
 * cover that layer globally). Fail-open by design — a broken guard must never
 * brick a session.
 */

function emit(decision, reason) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: decision,
        permissionDecisionReason: reason,
      },
    }),
  );
  process.exit(0);
}

let input = "";
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", () => {
  try {
    run(JSON.parse(input));
  } catch {
    process.exit(0);
  }
  process.exit(0);
});

function run(data) {
  const tool = String(data.tool_name || "");
  if (!/^mcp__supabase__/i.test(tool)) return;
  const ti = data.tool_input || {};
  const sql = String(ti.query ?? ti.sql ?? "");
  if (!sql) return;

  // cron: function-call forms and direct DML; plain reads stay silent.
  if (
    /\bcron\s*\.\s*(schedule|unschedule|alter_job)\s*\(/i.test(sql) ||
    /\b(insert\s+into|update|delete\s+from)\s+cron\s*\./i.test(sql)
  ) {
    emit("ask", "This SQL changes production cron jobs. Needs Roman's explicit yes.");
  }
  // vault: writes are SELECT-invoked; decrypted reads expose secret VALUES.
  if (
    /\bvault\s*\.\s*(create_secret|update_secret|delete_secret)\b/i.test(sql) ||
    /\b(insert\s+into|update|delete\s+from)\s+vault\s*\./i.test(sql)
  ) {
    emit("ask", "This SQL writes a production secret (vault). Needs Roman's explicit yes.");
  }
  if (/\bvault\s*\.\s*decrypted_secrets\b/i.test(sql)) {
    emit(
      "ask",
      "This SQL reads DECRYPTED secret values into the chat — names only. Needs Roman's explicit yes.",
    );
  }
  // destructive: comment/whitespace tolerant.
  if (
    /\bdrop(\s|\/\*[\s\S]*?\*\/)+(table|schema|database)\b/i.test(sql) ||
    /\btruncate\b/i.test(sql)
  ) {
    emit(
      "ask",
      "Destructive statement (DROP/TRUNCATE) on a live database. Needs Roman's explicit yes.",
    );
  }
}
