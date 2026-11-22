---
name: my-advisor
description: Consult the separate GPT-6.2 Astra advisor on an explicit request or at a consequential decision, repeated failure, or unresolved risk in a Codex task.
---

# My Advisor

Keep the model selected in the current chat as the primary agent. The primary agent owns the plan, edits, checks, and final answer.

Consult before committing to a decision that could break existing behavior, including ambiguous changes to databases, integrations, queues, schedulers, or concurrency. Consult after two distinct, evidence-based attempts have failed to fix a problem. Consult before finishing complex work if a specific material risk still lacks verification. Consult whenever the user asks. Routine edits need no consultation. One or two calls usually suffice. Consult again for new evidence or a remaining material risk.

1. Use Codex's native subagent tool. Select the installed `my-advisor` role when the tool exposes it. When the tool only exposes model and reasoning overrides, read `.codex/agents/my-advisor.toml` and include its full advisor instructions in the spawn message. In either case, require `gpt-6.2-astra` at `high` and a separate context (set `fork_turns` to `none` if exposed). Include the handoff in the spawn message. If the tool cannot select the required model and effort or the runtime reports another model, tell the user that the Astra consultation could not be completed. Do not switch models or present your own review as the consultation.
2. Give the advisor the goal, constraints, the specific question, and the current plan or alternatives. Include relevant paths, code excerpts, diff hunks, and check results in the handoff when available. Include callers, invariants, and operational context when they can change the answer. Share enough evidence to decide the question, keeping unrelated material and secrets out. Identify what is still unknown.
3. Wait for the advisor and check its claims against the code and test results. Ask for a recommendation, concrete risks tied to code, and checks that would resolve them. The primary agent decides what to act on and reports any remaining uncertainty.
