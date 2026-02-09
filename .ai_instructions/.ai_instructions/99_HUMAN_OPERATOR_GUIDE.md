# HUMAN OPERATOR GUIDE: ZELQIVO AI WORKFLOW

This document outlines the standard operating procedure (SOP) for interacting with the Zelqivo AI Engineering Team within the IDE.

## PHASE 1: INITIALIZATION (The Handshake)
At the start of every coding session or new chat window, copy-paste this command to "boot up" the team:

> **"Initialize Zelqivo Team. Load context from `.ai_instructions`. I am ready to start. Current Mode: Interactive Team."**

---

## PHASE 2: THE LOOP (Standard Work)
You do not need to manually summon agents for every task. Simply state your objective. The System will automatically assess complexity and activate the necessary agents.

**Example Request:**
> "I want to add a button that translates video subtitles to Spanish."

**Expected Auto-Response:**
* **[PRODUCT]:** Asks about scope (Premium vs. Free? MVP first?).
* **[ARCHITECT]:** Proposes an async API integration (e.g., Celery task).
* **[UX]:** Suggests a progress loader UI to prevent freezing.
* **[DEV]:** Generates the implementation code.

---

## PHASE 3: MANUAL OVERRIDE (Directing Agents)
If the AI moves too fast, misses a detail, or you need specific expertise, use **Agent Tags** to force a specific mode:

* **`@SEC`** -> "Review this code for vulnerabilities (XSS, Injection)."
* **`@QA`** -> "Write unit tests for this function, covering edge cases."
* **`@PRODUCT`** -> "Are we over-engineering this? Is this critical for MVP?"
* **`@ARCHITECT`** -> "Will this scale to 10,000 concurrent users?"

---

## PHASE 4: STATE PRESERVATION (Commit)
When a feature is complete and tested, ask the AI to summarize the work for Git:

> **"Generate a Semantic Commit Message based on the changes we made."**

---

## PRO TIP: CONTEXT REFRESH
If the session gets too long and the AI starts forgetting rules, type:
> **"Reset Context. Reload rules from `.ai_instructions/00_MASTER.md`. Let's continue."**