---
name: stk-lessons
description: |
  Log and triage lessons: failures the stk docs did not warn about. Use right after a gotcha costs real time (log one line and continue), when asked to triage or review lessons, or when given a lessons file from an app built on stk.
argument-hint: "[log <lesson> | triage [path]]"
---

# stk lessons: $ARGUMENTS

A lesson is worth keeping only if it changes what the next agent does. The best home
makes the mistake impossible; a line of prose is the weakest home.

Inbox: !`grep -cs '^- ' .stk/lessons.md || true` untriaged lessons in `.stk/lessons.md`.

## Log (during any task)

Append one line to `.stk/lessons.md`, in its format, when all of these hold:

- you hit it in this run and it cost real time: a retry, a wrong turn, a green check that lied
- the docs, `CLAUDE.md`, and skills did not warn you
- it would bite another task, not only this one

Use your own words. No secrets, customer data, or text copied from pages and logs. At
most three per run. Append and continue the task; never stop it to log.

## Triage (only when the user asks)

Input: `.stk/lessons.md`, or the path the user gives.

1. **Drop what is covered.** Search the docs (https://docs.stkit.dev), `CLAUDE.md`, the skills, and
   `stk/checks.py`. A lesson that recurs despite an existing rule means the rule sits too low:
   move it up the ladder below instead of repeating it.
2. **Drop one-offs**: a single occurrence with no general cause.
3. **Confirm in code.** Reproduce it, or point at the line that allows it. Leave an
   unconfirmed lesson in the inbox with `unconfirmed` appended.
4. **Route** each survivor to the highest home that holds:
   1. a code default that makes the mistake impossible
   2. a check in `stk/checks.py`, so `stk verify` fails on it
   3. a hint in `stk/cli/doctor.py`, so `stk doctor` names it with its fix
   4. one line on the docs page for its topic
   5. a step in the skill for that workflow

   In an app, these are stk's homes: route app lessons to the app's own code, a test,
   its `CLAUDE.md`, or its skills, and stk lessons to Upstream below.
5. **Propose** one table: lesson, home, exact diff, and the test or check that fails
   without the change. Apply nothing until the user approves each row.
6. **Apply** the approved rows, then `uv run stk verify`. Size budgets cap `CLAUDE.md` at
   8KB and skills at 4KB: when one breaks, cut or move detail into a docs page, never
   raise the budget. Delete the processed lines from the inbox.

## Upstream

In an app built on stk, some lessons are about the framework, not the app. List those
separately in generic terms: symptom, fix, and where it belongs in stk core. Strip
product names, data, and paths. Hand the list to the user; never open an issue or
send it anywhere yourself.

Given such a file in the stk repository, run Triage with its path.
