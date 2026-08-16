---
name: job-search
description: Search for job openings and help the user evaluate, track, and apply to them. Use this skill whenever the user asks to find jobs, search openings, look for roles, check what's hiring, compare postings, or wants help figuring out which companies/roles to target — even if they don't say "job search" explicitly (e.g. "what's out there for an AI engineer in Riyadh", "any ML roles at Google", "find me something remote"). Also use it when the user wants to save a company/role for later, update their application status, or log that they applied somewhere.
---

# Job Search

Helps the user find relevant job openings, evaluate them against their profile, and keep their application pipeline (companies, statuses, notes) up to date — end to end, not just a raw list of links.

## When to use this skill

Trigger on any of:
- Direct requests: "find me jobs", "search for AI engineer roles", "what's hiring in Islamabad"
- Indirect requests: "is there anything for someone with my background", "should I look at Google or Meta right now", "anything remote and ML-focused"
- Pipeline management: "mark this as applied", "save this company for later", "what have I applied to so far"
- Comparison requests: "which of these roles fits me better"

Do **not** trigger for generic career-advice questions with no openings involved (resume review, interview prep, salary negotiation) — those are separate skills/flows.

## Available tools

This skill expects the following tools to be available (names match the CareerPilot backend). If your tool names differ, update this section to match — the workflow logic stays the same either way.

| Tool | Purpose |
|---|---|
| `recall_similar_notes` | Pull prior context on the user's target roles, companies already discussed, and preferences before searching, so you don't repeat work or contradict earlier findings. |
| `search_jobs` | Query live job postings by role, location, seniority, and other filters. |
| `save_company_note` | Persist a note about a specific company/role the user is interested in (why it's a fit, concerns, salary info, contact, etc). |
| `update_application_status` | Update the status of an existing application (e.g. `saved → applied → interviewing → offer/rejected`). |
| `log_application` | Record that the user applied to a specific role, with date, source, and role/company metadata. |
| `update_profile` | Persist any new preference or fact the user reveals mid-search (e.g. "actually I don't want onsite roles anymore"). |

## Workflow

### 1. Recall context first

Before searching, call `recall_similar_notes` (or equivalent) to check:
- Target role(s) and seniority level already on file
- Preferred locations / remote vs. onsite / visa or relocation constraints
- Companies already discussed, saved, or rejected
- Any hard constraints (salary floor, industry exclusions, must/must-not-have)

Don't ask the user to repeat information that's already in memory. Only ask a clarifying question if something essential is missing (target role, location/remote preference) **and** isn't inferable from the conversation.

### 2. Build the search query

Construct `search_jobs` queries that are specific, not just the user's raw phrasing:
- Include role title(s) **and** close synonyms (e.g. "AI Engineer" + "ML Engineer" + "Applied AI") when the user's target role has overlapping titles across companies
- Include location or explicitly search "remote"
- Run multiple narrower searches rather than one broad one if the role/location combination is ambiguous — this returns more relevant results than a single vague query
- Prefer recent postings; deprioritize or flag listings that are clearly stale (>60 days old, no explicit date, or already gone in a follow-up check)

### 3. Filter and rank before presenting

Never dump raw search results. Filter out:
- Duplicate postings (same role/company from multiple sources)
- Roles that clearly don't match the user's stated seniority or hard constraints
- Obvious scraper/aggregator noise (listing farms with no real posting behind them)

Rank what remains by fit: role-title match, seniority match, location/remote match, and — if available in memory — company reputation or user's stated interest in that company.

Cap what you show at once to a reasonable number (roughly 5–8 strong matches) rather than an overwhelming list. Offer to search further/broaden if the user wants more.

### 4. Present results clearly

For each job, surface:
- **Role title** and **company**
- **Location** (and remote/hybrid/onsite status)
- **Why it's a fit** — one line tying it back to the user's profile/goals, not generic filler
- **Link** to the actual posting

Group by company or by fit-tier if there are more than ~5 results, so the response is scannable, not a wall of text.

### 5. Act on what the user decides

- If the user says they like a company/role → call `save_company_note` with a short note capturing why (their words, not a generic summary) so it's retrievable later.
- If the user says they applied → call `log_application` with role, company, date, and source (where they applied from).
- If the user is updating an existing application's status → call `update_application_status`, not `log_application` (don't create a duplicate entry).
- If the user reveals a new preference mid-conversation (e.g. "I'd take a pay cut for remote") → call `update_profile` so future searches respect it automatically.

### 6. Handle empty or weak results honestly

If `search_jobs` returns nothing strong:
- Say so plainly rather than stretching a weak match to look like a fit
- Suggest a concrete adjustment: broaden location, adjust title, relax seniority, or try again in a few days
- Don't fabricate postings or details — every link and detail must come from the actual tool result

## Output tone

- Be direct about fit, including weak fits — the user is job hunting, not looking for flattery
- Skip corporate filler ("exciting opportunity", "great culture fit") unless it's a specific, factual detail from the posting
- When in doubt about a close call (e.g. borderline seniority), say so explicitly rather than silently deciding for the user