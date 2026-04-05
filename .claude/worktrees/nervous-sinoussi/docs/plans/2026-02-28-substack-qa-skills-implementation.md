# Substack QA Skills Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create two standalone Claude Code skills for sequential pre-publication QA of Substack long-form content.

**Architecture:** Two self-contained SKILL.md files in `~/.claude/skills/`. No plugin wrapper, no reference files. Each skill defines its own frontmatter, workflow instructions, audit criteria, and output format.

**Tech Stack:** Markdown (SKILL.md format with YAML frontmatter)

**Design doc:** `docs/plans/2026-02-28-substack-qa-skills-design.md`

---

### Task 1: Create directory structure

**Files:**
- Create: `~/.claude/skills/creative-qa/` (directory)
- Create: `~/.claude/skills/publication-proofreader/` (directory)

**Step 1: Create both skill directories**

Run:
```bash
mkdir -p ~/.claude/skills/creative-qa ~/.claude/skills/publication-proofreader
```

Expected: Both directories exist, no errors.

---

### Task 2: Write Creative QA Check SKILL.md

**Files:**
- Create: `~/.claude/skills/creative-qa/SKILL.md`

**Step 1: Write the full SKILL.md file**

Write the Creative QA Check skill to `~/.claude/skills/creative-qa/SKILL.md`. The file must contain:

**Frontmatter:**
- `name: creative-qa`
- `description:` Must include trigger phrases: "creative QA", "QA check", "review my draft", "is this ready to publish", "check my post", "check my article", strategic quality assessment of written content before publication. Mention this is stage 1 of a two-stage QA system.

**Body sections (in order):**

1. **Overview** -- What this skill does: strategic quality assessment of long-form content before publication. Stage 1 of a two-stage system. Run this first, fix issues, then run Publication Proofreader.

2. **Locating the Draft** -- Instructions for Claude to check if draft text is already in conversation (pasted or read from file). If not, ask user to either paste it or provide a file path to read.

3. **Brand Context Discovery** -- Instructions for Claude to search for brand context in this order:
   - `brand-guide.md`, `voice-guide.md`, or `brand-positioning.md` in current project root
   - `~/.claude/skills/brand-context/` directory
   - Files matching `*brand*`, `*voice*`, `*positioning*` via glob
   - If nothing found, ask the user or proceed without it

4. **Tone** -- Adapt to the active companion personality in the conversation thread. Honest critique, never sycophantic. Opinionated and direct. Does not soften bad news. If no companion context is present, default to direct and professional.

5. **Audit Categories** -- All six categories with their specific criteria:
   - Voice & Brand Authenticity
   - Structure & Content Flow
   - Scannability
   - Strategic Elements
   - Substack-Specific
   - Accessibility & Clarity
   (Full criteria per category from design doc)

6. **Output Format** -- Exact output structure:
   - Brief overall assessment (2-3 sentences, blunt)
   - Findings grouped: Critical / Important / Nice to have
   - Each finding references specific section/paragraph
   - Ends with: "Fix the Critical items, then run the Publication Proofreader."

7. **What This Skill Does NOT Do** -- Explicitly: no typo fixing, no grammar checking, no formatting fixes. That is the Proofreader's job.

**Step 2: Verify the file**

Run:
```bash
cat ~/.claude/skills/creative-qa/SKILL.md | head -5
```

Expected: Should show the YAML frontmatter opening with `---` and `name: creative-qa`.

**Step 3: Commit**

```bash
git add ~/.claude/skills/creative-qa/SKILL.md
git commit -m "feat: add Creative QA Check skill (stage 1 of Substack QA)"
```

Note: This file is outside the repo. If git add fails because the path is outside the worktree, skip the commit -- standalone files don't need to be tracked in this repo.

---

### Task 3: Write Publication Proofreader SKILL.md

**Files:**
- Create: `~/.claude/skills/publication-proofreader/SKILL.md`

**Step 1: Write the full SKILL.md file**

Write the Publication Proofreader skill to `~/.claude/skills/publication-proofreader/SKILL.md`. The file must contain:

**Frontmatter:**
- `name: publication-proofreader`
- `description:` Must include trigger phrases: "proofread", "publication proofreader", "final polish", "ready to publish check", "pre-publish check", technical polish before publishing. Mention this is stage 2 of a two-stage QA system, run after Creative QA issues are fixed.

**Body sections (in order):**

1. **Overview** -- What this skill does: technical polish and execution-level QA. Stage 2 of a two-stage system. Assumes strategic issues are already fixed. Produces copy-paste-ready fixes.

2. **Locating the Draft** -- Same instructions as Creative QA for finding draft content.

3. **Tone** -- Adapt to active companion personality. Clinical and factual. No sycophancy, but also not opinionated about strategy. Reports what needs fixing with before/after examples. If no companion context, default to clinical.

4. **Audit Categories** -- All seven categories with specific criteria:
   - Language & Grammar
   - Formatting Consistency
   - Mobile Optimization
   - Visual Elements
   - Links & Technical
   - Basic SEO Check
   - Headline & Subtitle Alternatives
   (Full criteria per category from design doc)

5. **Output Format** -- Exact output structure:
   - Checklist grouped by category
   - Each item: fix needed / looks good
   - Before/after examples for every fix (copy-paste ready)
   - Headline alternatives at end (3-5 headlines, 2-3 subtitles, each noting what it optimizes for)
   - Final summary: word count, estimated reading time, overall readiness assessment

6. **What This Skill Does NOT Do** -- Explicitly: no strategic feedback. Never says "restructure your opening" or "this section is weak." Strategy is settled. Only execution-level issues.

**Step 2: Verify the file**

Run:
```bash
cat ~/.claude/skills/publication-proofreader/SKILL.md | head -5
```

Expected: Should show the YAML frontmatter opening with `---` and `name: publication-proofreader`.

**Step 3: Commit (if trackable)**

Same note as Task 2 -- these files live outside the repo.

---

### Task 4: Verification

**Step 1: Verify both files exist and have correct frontmatter**

Run:
```bash
head -10 ~/.claude/skills/creative-qa/SKILL.md && echo "---" && head -10 ~/.claude/skills/publication-proofreader/SKILL.md
```

Expected: Both files show valid YAML frontmatter with correct names and descriptions.

**Step 2: Check file sizes are reasonable**

Run:
```bash
wc -l ~/.claude/skills/creative-qa/SKILL.md ~/.claude/skills/publication-proofreader/SKILL.md
```

Expected: Each file should be roughly 150-250 lines. If significantly shorter, content may be missing.
