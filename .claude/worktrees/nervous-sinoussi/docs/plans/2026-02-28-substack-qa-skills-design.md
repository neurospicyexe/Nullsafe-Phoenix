# Two-Stage Pre-Publication QA System -- Design Document

**Date:** 2026-02-28
**Status:** Approved
**Delivery:** Two standalone SKILL.md files in `~/.claude/skills/`

## Problem

After hours of drafting long-form Substack content, the author is blind to strategic mistakes (weak hooks, voice drift, structural gaps) and technical issues (typos, mobile formatting, weak headlines). A systematic final check is needed -- one that catches both strategic and execution-level problems, in the right order.

## Core Design Decision

Two separate skills, run sequentially. Never combined. Fix strategy first, then polish execution. This separation was validated by the author -- combined approaches produced unprioritizable feedback.

## File Structure

```
~/.claude/skills/
├── creative-qa/
│   └── SKILL.md
└── publication-proofreader/
    └── SKILL.md
```

No reference files, no plugin wrapper. Each skill is self-contained.

## Shared Conventions

### Draft Input

Both skills accept draft content two ways:
- Already present in the conversation (pasted text or file read earlier)
- If not found, ask the user to paste it or provide a file path

### Brand Context Discovery

Both skills search for brand context in this order:
1. `brand-guide.md`, `voice-guide.md`, or `brand-positioning.md` in current project root
2. `~/.claude/skills/brand-context/` directory (global brand files)
3. Files matching `*brand*`, `*voice*`, `*positioning*` via glob
4. If nothing found, ask the user or proceed without it

### Tone

- Adapts to the active companion personality from the conversation thread
- Honest critique, never sycophantic
- Creative QA: opinionated and direct
- Proofreader: clinical and factual
- Neither softens bad news

### Priority Tiers

Both skills use three tiers:
- **Critical** -- Will hurt engagement, confuse readers, or misrepresent voice
- **Important** -- Noticeable quality issues that should be fixed
- **Nice to have** -- Polish items, take-or-leave

## Skill 1: Creative QA Check

### Triggers

"creative QA", "QA check", "review my draft", "is this ready to publish", "check my post", strategic quality assessment of written content.

### Workflow

1. Locate draft (already in conversation, or ask)
2. Search for brand context files
3. Audit against six categories
4. Return prioritized findings with specific section/paragraph references

### Six Audit Categories

1. **Voice & Brand Authenticity** -- Voice drift from brand positioning. British colloquialisms that might confuse broader audience. Tone consistency throughout.

2. **Structure & Content Flow** -- Opening hook strength. Transition quality. Emotional arc. Title promise delivered. Sections that lose momentum or repeat.

3. **Scannability** -- Can readers skim for main points? Header hierarchy clear? Pull quote opportunities (1-2 standout sentences). Dense text blocks flagged.

4. **Strategic Elements** -- Primary/secondary keywords. Headline optimized for search and curiosity. Subheadline clear with keywords. Section headers compelling not just descriptive. Internal link opportunities.

5. **Substack-Specific** -- First 140 chars compelling for email preview. Pull quotes worth highlighting. Opening works as both email and web.

6. **Accessibility & Clarity** -- Reading level appropriate. Unexplained jargon. Sentence length variation (ADHD readers). Assumptions about reader knowledge.

### Output Format

- Brief overall assessment (2-3 sentences, blunt)
- Findings grouped by priority tier (Critical / Important / Nice to have)
- Each finding references specific section/paragraph
- Ends with direction to fix Critical items, then run Publication Proofreader

## Skill 2: Publication Proofreader

### Triggers

"proofread", "publication proofreader", "final polish", "ready to publish check", "pre-publish check", after fixing Creative QA issues.

### Workflow

1. Locate draft (already in conversation, or ask)
2. Run through seven technical audit categories
3. Return copy-paste-ready checklist with before/after examples
4. Generate headline and subtitle alternatives

### Seven Audit Categories

1. **Language & Grammar** -- Typos, grammar, header capitalization, Oxford comma removal, consistent punctuation.

2. **Formatting Consistency** -- Curly quotes not straight, bullet/numbered list consistency, bold/italic usage, heading hierarchy.

3. **Mobile Optimization** -- 1-3-1 and 1-2-1 paragraph formatting, no paragraphs >3-4 mobile lines, lists breaking up dense text, sufficient white space.

4. **Visual Elements** -- Alt text for all images (descriptive, accessible, contextual), image placement, caption recommendations.

5. **Links & Technical** -- Link functionality (flag suspicious), descriptive link text (not "click here"), strategic internal links, no placeholder text.

6. **Basic SEO Check** -- Title optimized, subtitle as meta description (compelling + clear + keywords), first 140 chars for email preview.

7. **Headline & Subtitle Alternatives** -- 3-5 headline alternatives with different angles/keywords. 2-3 subtitle alternatives. Each notes what it optimizes for (curiosity, SEO, clarity, emotional pull).

### Output Format

- Checklist format grouped by category
- Each item: fix needed / looks good
- Before/after examples for every fix (copy-paste ready)
- Headline alternatives section at end
- Final summary: word count, estimated reading time, overall readiness

### Key Boundary

This skill never gives strategic feedback. No "restructure your opening." It assumes strategy is settled and only catches execution-level issues.
