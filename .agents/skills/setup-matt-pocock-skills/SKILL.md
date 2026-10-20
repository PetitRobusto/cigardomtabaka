---
name: setup-matt-pocock-skills
description: Configure repository issue-tracker routing, triage-label mappings, and optional domain-document pointers for engineering skills. Use when setup is explicitly requested or an issue operation lacks essential routing information. TDD, architecture exploration, diagnosis, and code explanations do not require this setup.
disable-model-invocation: true
---

# Setup Engineering Skills

Record the minimum repository configuration needed by the current task. Reuse existing conventions and session decisions; setup is not a prerequisite for ordinary engineering work.

## Decide whether setup is needed

- `to-issues`, `to-prd`, and `triage` need a known tracker and destination when they read or publish issues. Label operations also need the relevant category and state mappings.
- A supplied issue URL or an existing repository convention may already provide enough context. Missing `docs/agents/` alone is not a blocker.
- TDD, architecture exploration, diagnosis, and explanations can read `CONTEXT.md`, `CONTEXT-MAP.md`, and relevant ADRs directly. Do not interrupt those tasks to configure issue tracking.
- A user asking for a local draft has not authorized publishing it to a tracker. Setup does not create remote issues, labels, or comments.

## Inspect and reuse

Read whichever sources are relevant:

- `AGENTS.md`, `CLAUDE.md`, and existing `docs/agents/*.md`.
- Git remotes and repository workflow documentation when identifying a tracker.
- Existing tracker labels through available read-only tools when labels are needed.
- `CONTEXT-MAP.md`, or root `CONTEXT.md` and `docs/adr/`, for domain layout.
- Existing local issue files, including `.scratch/`, when local tracking is in use.

Do not replace established configuration with defaults. A GitHub or GitLab remote suggests a tracker; it does not prove where the user tracks issues. An explicit destination or documented convention is stronger evidence.

## Resolve only missing decisions

If the task already establishes the destination and conventions, proceed without another approval round. Ask a concise question only when unresolved alternatives affect where work will be read or written.

For trackers, support the existing choice: GitHub, GitLab, local Markdown, or another connected tracker. Use the appropriate available tool rather than assuming a specific CLI is installed.

For triage, map the five state roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) and category roles (`bug`, `enhancement`) to existing labels. Do not silently create or rename remote labels. When mappings are unknown, keep them unresolved until needed rather than claiming the tracker is configured.

Infer domain layout from existing files. Ask only when multiple plausible contexts exist and the task does not identify the relevant one.

## Write only needed configuration

When setup is authorized, summarize the intended local changes and write them without requiring another review of decisions already made. Preserve unrelated content and user edits.

- Update the file already containing the `## Agent skills` block.
- If no block exists, follow the repository's agent-instruction convention. When both files exist, prefer the one governing the current agent unless they document another canonical location.
- Create only the relevant files under `docs/agents/`; do not scaffold empty configuration for unrelated workflows.
- Add links only to files actually present or created. Avoid duplicating domain rules already maintained in `CONTEXT.md` or ADRs.

Use these seed templates only for the chosen route:

- [GitHub tracker](issue-tracker-github.md)
- [GitLab tracker](issue-tracker-gitlab.md)
- [Local Markdown tracker](issue-tracker-local.md)
- [Triage labels](triage-labels.md), extending it with the category mappings when needed
- [Domain documentation](domain.md), only when a central pointer adds useful context

A configured block can contain only the applicable sections:

```markdown
## Agent skills

### Issue tracker

Issues are tracked in the documented project destination. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the mappings in `docs/agents/triage-labels.md`.

### Domain docs

Read root `CONTEXT.md` and relevant decisions in `docs/adr/`.
```

## Verify and finish

Check that links resolve and recorded destinations and mappings match inspected evidence. Report what was configured and any genuinely unresolved choices. Return to the original authorized task; do not require setup to be run again when the existing configuration is sufficient.
