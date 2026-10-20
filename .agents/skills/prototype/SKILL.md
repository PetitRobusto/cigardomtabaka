---
name: prototype
description: Build a disposable logic prototype or UI design preview to answer a concrete design question. Use when the user requests a prototype, wants to try a state model, or compare UI approaches. Follow the repository's designated design-preview workflow before creating UI variants in application code.
---

# Prototype

A prototype is **throwaway code that answers a question**. The question decides the shape.

## Pick a branch

Identify which question is being answered — from the user's prompt, the surrounding code, or by asking if the user is around:

- **"Does this logic / state model feel right?"** → [LOGIC.md](LOGIC.md). Build a tiny interactive terminal app that pushes the state machine through cases that are hard to reason about on paper.
- **"What should this look like?"** → [UI.md](UI.md). Start in the repository's designated design-preview workspace. Use application routes only when that workflow permits them.

The two branches produce very different artifacts — getting this wrong wastes the whole prototype. If the question is genuinely ambiguous and the user isn't reachable, default to whichever branch better matches the surrounding code (a backend module → logic; a page or component → UI) and state the assumption at the top of the prototype.

## Rules that apply to both

1. **Disposable and isolated.** Mark prototype code clearly and keep it out of production execution. Respect the repository's designated preview location; do not add a product route just to bypass that workflow.
2. **Easy to try.** Give one run command for local code, or the returned preview link for a design workspace.
3. **No persistence by default.** Use in-memory state and synthetic fixtures. If persistence is the question, use an explicitly separate disposable database and verify its target before any write. Do not connect prototypes to production mutations. In this Django repository, explicitly enable `DJANGO_DEBUG=True` for local work; it does not replace a dedicated disposable database when one is required.
4. **Keep validation proportional.** Skip production polish and exhaustive tests for a disposable shell, but check that it runs and demonstrates the intended transitions. Add focused checks when needed to avoid misleading conclusions about money, inventory, or other business invariants.
5. **Surface the state.** After every action (logic) or on every variant switch (UI), print or render the full relevant state so the user can see what changed.
6. **Separate exploration from shipping.** Capture the result. Integrate only when implementation is within the user's request; before reusing any logic or UI, add appropriate behavior tests, error handling, and repository-required review. A successful demo is not production validation. Remove only disposable artifacts from this task when no longer needed.

## When done

The _answer_ is the only thing worth keeping from a prototype. Capture it somewhere durable (commit message, ADR, issue, or a `NOTES.md` next to the prototype) along with the question it was answering. If the user is around, that capture is a quick conversation; if not, leave the placeholder so they (or you, on the next pass) can fill in the verdict before deleting the prototype.
