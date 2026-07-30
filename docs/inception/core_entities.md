# BuildWatch Inception — Core entities (platform core)

**Product definition:** BuildWatch Inception is an open collaboration and decision platform where any sponsor, business owner, and technical team co-develop a living brief, resolve asset custody and resource commitment, and earn a project identity through explicit gates — with sector-specific behaviour supplied by profiles, not hardcoded in the core.

Sector examples (housing, dams, roads, telecom, lunar facilities) are **profiles**. The core stays domain-neutral.

## Minimal entity list

| Entity | Purpose |
|--------|---------|
| **Initiative** | Pre-project collaboration space. Has no BuildWatch project ID until concept gate is passed. |
| **ProgrammeProfile** | Loaded JSON/config: lanes, prompts, custody types, funding types, gates, downstream modules. |
| **LivingBrief** | One living document for the initiative (versioned snapshot on each decision). |
| **LaneContribution** | Content block on the brief scoped to a lane (`mandate` / `requirements` / `feasibility`). |
| **Participant** | Person/org on the initiative with a role (`SPONSOR`, `BUSINESS_OWNER`, `TECHNICAL_LEAD`, `LEGAL`, `FINANCE`). |
| **CustodyRecord** | Asset/site/rights custody (land, ROW, spectrum, orbital slot, …) — types from profile. |
| **CommitmentRecord** | Resource commitment / funding envelope — sources from profile. |
| **ThreadComment** | Discussion anchored to a lane, prompt, or record. |
| **Decision** | Explicit gate outcome (who, when, note, brief version snapshot). |
| **EvidenceAttachment** | File linked to custody, commitment, or lane. |

## Universal lanes (semantics fixed; labels from profile)

| Lane id | Meaning |
|---------|---------|
| `mandate` | WHY — case, outcomes, strategic fit |
| `requirements` | WHAT — users, scale, standards |
| `feasibility` | HOW + HOW MUCH — approach, custody, OME / cost |

## Decision gates (same flow for every profile)

| Gate id | Unlocks |
|---------|---------|
| `concept_approved` | Project identity minted; design/development chapter |
| `design_direction_approved` | Documentation / package assembly |
| `package_approved` | Downstream module (e.g. tender publish, RFP, study phase) |

Gate **readiness expressions** and required evidence are profile-defined.

## What must not live in core code

- Kenya-only land routes as fixed enums
- BOQ / tender as mandatory lifecycle
- Housing- or Emurua-specific fields on core entities
- Org names (Ministry of Works, etc.) — those are tenant data

## Profile ? downstream modules (optional exits)

| Profile family | After `package_approved` might open |
|----------------|-------------------------------------|
| Buildings / works | Tender exchange (existing) |
| Linear infrastructure | Corridor package / works tender |
| ICT / telecom | License + vendor RFP |
| Space / extreme | Phase-0 study / agency budget (no BOQ) |

## Status of this document

Stable enough to drive Phase-1 UI and a future Django migration. Profiles live under `buildwatch/inception/profiles/`.
