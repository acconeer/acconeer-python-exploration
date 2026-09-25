---
name: code-review-local
description: Reviews a local git commit by inspecting its diff and providing structured, actionable feedback.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/gather_commit_info.sh *)
---

# Code Review Skill

Act as a senior Python developer and signal processing expert. Your role is to perform thorough
code reviews of data processing algorithms, evaluating correctness, efficiency, readability, and
engineering best practices.

## Step 1: Identify the commit

Review the commit the user names (a ref, SHA or branch), or `HEAD` if none. A range (`A..B`) is
reviewed commit by commit in one report: one summary sentence per commit, one table with each
Status the worst across commits, and each finding and positive tagged with its commit, as in
`F1 [abc1234 file:line]`. "The commit" in any rule means the finding's commit. Run the gates
once, in a worktree at the range's last commit, and note on the Gates line that the copyright
check then covers only that commit's files.

## Step 2: Gather commit information

!`${CLAUDE_SKILL_DIR}/scripts/gather_commit_info.sh $ARGUMENTS`

If that reports no git repository, tell the user and stop. If it reports no such commit or range,
resolve what the user named to a ref and rerun the script with it.

## Step 3: Review criteria

Systematically review the diff across these dimensions:

### 3a. Correctness & Logic

- Are there obvious bugs or off-by-one errors?
- Are edge cases handled (null/empty/boundary values)?
- Could this change introduce regressions?
- If the commit presents itself as a move or refactor, diff the old content against the new and
  report every change in behavior or content, however small.
- What do outside consumers lose: public API, persisted formats, published URLs or anchors?
- Are error paths and exceptions handled properly?

### 3b. Security

- Are there injections risks (shell, path traversal)?
- Are secrets or credentials accidentally committed?
- Are inputs validated and sanitized (e.g. `eval`, `exec`, `pickle`, `os.system`, `subprocess`)?
- Are permissions or access controls affected?

### 3c. Performance

- Are there unnecessary loops, or expensive operations in hot paths?
- Are there memory leaks or unbounded allocations?

### 3d. Readability & Maintainability

- Are names (variables, functions, files) clear and consistent with the surrounding codebase?
- Is complex logic explained with comments?
- Is there dead code, commented-out blocks, or debug statements left in?
- Is there unnecessary duplication that should be extracted?
- Is the code idiomatic Python (Pythonic); e.g. does it favor built-ins, comprehensions, unpacking,
  and standard libraries over verbose or non-native patterns?
- Do comments and strings avoid em dashes (—) where standard punctuation (hyphens, colons, or
  parentheses) would be correct?

### 3e. Domain correctness (signal processing)

- Are array shapes and dimension conventions explicit and consistent (e.g. `(N,)` vs `(channels, samples)`)?
- Are sample rate and physical units (Hz, dB, radians/sample) treated as explicit parameters, not hardcoded assumptions?
- Are numerical precision choices (float32 vs float64) appropriate for the operation (e.g. FFT)?
- Is spectral analysis correct - windowing applied, Nyquist limit respected, output length intentional?
- Is DC offset handled or explicitly ignored?

### 3f. Tests

- Are there new tests for new behavior?
- Do existing tests cover the changed paths?
- Are tests meaningful (not just asserting trivially true things)?

### 3g. Commit hygiene

- Does the commit message clearly explain *why* (not just *what*)?
- Is the commit focused, or does it mix unrelated concerns?
- Does the commit message describe what's actually changed?

## Step 4: Verify

Check every finding before reporting it: read the surrounding code, grep for the other callers,
or reproduce it with a command. Drop what doesn't hold up. Mark a finding that can't be checked
as unverified in the finding itself, and say what would settle it. A claim the commit relies
on that no gate here can check (a server's behaviour, hardware, another repo) is such a
finding, not a gate note.

Run the narrowest gate that fits the change: `hatch check code` and `hatch check fmt`, the
touched test module on one interpreter (`hatch test -py=<version> <path>`), or
`hatch run docs:build` for docs. Keep only the failing tail of the output. If a gate can't run
here, say which one and why. CLAUDE.md's Commands section says how to invoke each gate.

Run gates in a worktree of the reviewed commit, so checkers that read HEAD see that commit:
`git worktree add --detach <scratch>/wt <commit>`, plus a second one at `<commit>^` when comparing
built output. Remove them with `git worktree remove` when done.

## Step 5: Output format

Use exactly this skeleton, keeping every heading except Positives even when it is empty:

````markdown
### 📋 Commit summary

<One or two sentences: what the commit does and why.>

| Dimension | Status | Findings |
|---|---|---|
| Correctness | ❌ | F1 |
| Security | ✅ | none |
| Performance | ✅ | none |
| Readability | ✅ | F2 |
| Domain correctness | ✅ | none |
| Tests | ✅ | none |
| Commit hygiene | ✅ | none |

### 🔴 Critical

**F1 [file:line] Short title.** What is wrong and why it matters.

### 🟡 Important

None.

### 🟢 Suggestions

**F2 [file:line] Short title.** ... (unverified: <what would settle it>)

### ✅ Positives

<One to three concrete things done well, or omit this heading if there are none.>

**🧪 Gates:** docs:build ✅, check fmt not run (<why>)

**⚖️ Verdict:** Approve / Approve with suggestions / Request changes

**🔧 Worth fixing:** F1 (fold)
````

- Critical: must fix before merging (bugs, security issues, data loss risk). Important: should
  fix (logic issues, missing error handling, performance problems). Suggestions: nice to have.
- Before filing a finding under Suggestions, ask whether it fails without an error (a fallthrough
  return, a swallowed exception, a placeholder left in output), whether the work the commit
  says comes next will hit it, or whether it breaks loading existing recordings or saved
  configs. If any holds, it goes under Important.
- Status is ❌ for any Critical finding, ⚠️ for any Important one, ✅ otherwise (Suggestions
  only, or none).
- Number findings F1, F2 and on in the order they appear, worst first within each heading, so
  a fix can be asked for by number. Every finding appears in the table under its dimension.
- Add a diff only when the fix isn't obvious from the prose.
- Verdict is Request changes if any finding is Critical or Important, Approve with suggestions
  if there are only Suggestions, and Approve if there are none.
- Gates lists each gate Step 4 ran with its result, and each one it couldn't run with why.
- Worth fixing lists the Critical and Important findings and nothing else, or "none". Mark it
  "(fold)" when the commit is local, or "(follow-up: already upstream)" when Step 2 found it
  upstream. For a range, name the commit: "(fold into abc1234)".
- Stop after the "Worth fixing" line. A fix waits to be asked for.
- Write tight: a finding is two or three sentences, the defect and its consequence. Leave out
  how you found it, restatements of the diff, and hedging. Tightness is for wording, not
  coverage: report every verified finding, minor ones under Suggestions.

## Notes

- Focus on the diff, not the entire file. Avoid commenting on code that wasn't changed unless it directly interacts with the changed code.
- Be direct but constructive. Explain *why* something is a problem, not just *that* it is.
- If the commit touches multiple languages or frameworks, apply language-appropriate idioms.
- If you can't determine intent from context, say so rather than guessing.
