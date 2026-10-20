---
name: tdd
description: Use the red-green-refactor loop when the user requests TDD or test-first development. Also useful for regression fixes where reproducing the failure first clarifies the behavior. Adding integration tests alone does not require adopting the entire workflow.
---

# Test-Driven Development

## Philosophy

**Core principle**: Tests should verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't.

**Good tests** are integration-style: they exercise real code paths through public APIs. They describe _what_ the system does, not _how_ it does it. A good test reads like a specification - "user can checkout with valid cart" tells you exactly what capability exists. These tests survive refactors because they don't care about internal structure.

**Bad tests** are coupled to implementation. They mock internal collaborators or test private methods without verifying a meaningful contract. The warning sign: your test breaks when you refactor, but behavior hasn't changed.

**Persisted business facts are observable behavior.** Exercise writes through the business command or public API, then inspect the test database when needed to verify inventory movements, ledger entries, audit records, idempotency, or rollback. Do not bypass the command under test by writing the expected result directly. Prefer a real isolated test database for these checks; never use production data.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Anti-Pattern: Horizontal Slices

**DO NOT write all tests first, then all implementation.** This is "horizontal slicing" - treating RED as "write all tests" and GREEN as "write all code."

This produces **crap tests**:

- Tests written in bulk test _imagined_ behavior, not _actual_ behavior
- You end up testing the _shape_ of things (data structures, function signatures) rather than user-facing behavior
- Tests become insensitive to real changes - they pass when behavior breaks, fail when behavior is fine
- You outrun your headlights, committing to test structure before understanding the implementation

**Correct approach**: Vertical slices via tracer bullets. One test → one implementation → repeat. Each test responds to what you learned from the previous cycle. Because you just wrote the code, you know exactly what behavior matters and how to verify it.

```
WRONG (horizontal):
  RED:   test1, test2, test3, test4, test5
  GREEN: impl1, impl2, impl3, impl4, impl5

RIGHT (vertical):
  RED→GREEN: test1→impl1
  RED→GREEN: test2→impl2
  RED→GREEN: test3→impl3
  ...
```

## Workflow

### 1. Planning

When exploring the codebase, use the project's domain glossary so that test names and interface vocabulary match the project's language, and respect ADRs in the area you're touching.

Read repository instructions and reuse requirements and decisions already established in the session. Identify the interface under test and briefly list its important behaviors. Proceed when these are clear; do not require separate approval of interfaces, tests, or a plan.

Resolve questions from the code first. Ask only when a missing business decision changes expected behavior, or an action needs authorization under repository rules. Existing authorization persists.

Scale preparation to risk. A small regression fix needs a reproducing test, not a formal design. For money, inventory, order state, permissions, or idempotency, cover the relevant invariants, success paths, and failure or rollback paths. Follow repository branching and review requirements.

Use [deep modules](deep-modules.md) and [testability](interface-design.md) guidance only when an interface change is actually needed; do not expand the task into an architecture refactor.

### 2. Tracer Bullet

Write ONE test that confirms ONE thing about the system:

```
RED:   Write test for first behavior → test fails
GREEN: Write minimal code to pass → test passes
```

This is your tracer bullet - proves the path works end-to-end.

### 3. Incremental Loop

For each remaining behavior:

```
RED:   Write next test → fails
GREEN: Minimal code to pass → passes
```

Rules:

- One test at a time
- Only enough code to pass current test
- Don't anticipate future tests
- Keep tests focused on observable behavior

### 4. Refactor

After all tests pass, look for [refactor candidates](refactoring.md):

- [ ] Extract duplication
- [ ] Deepen modules (move complexity behind simple interfaces)
- [ ] Apply SOLID principles where natural
- [ ] Consider what new code reveals about existing code
- [ ] Run tests after each refactor step

**Never refactor while RED.** Get to GREEN first.

## Checklist Per Cycle

```
[ ] Test describes behavior, not implementation
[ ] Actions use the business/public interface; assertions verify observable results or persisted business facts
[ ] Test would survive internal refactor
[ ] Code is minimal for this test
[ ] No speculative features added
```
