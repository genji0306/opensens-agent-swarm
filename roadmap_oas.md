# OAS Roadmap — OpenSens Agent Swarm

## Strategic role

OAS should be the **control plane** of OpenSens Darklab.

It is not merely a chat-based agent swarm. Its real function is to:
- interpret research intent
- orchestrate campaigns
- allocate models, tools, and compute
- enforce governance, budgets, and approvals
- maintain memory and provenance
- dispatch work to Parallax, OAE, OPAD, and DAMD

Given current maturity, OAS should remain the most stable and central module in the Darklab stack.

---

## Current baseline

Current strengths already visible:
- routing and dispatch
- governed campaign flow
- memory injection and storage
- budget enforcement
- DRVP event streaming and office visualization
- multi-node cluster topology
- tiered model routing and agent personas

This means OAS is already beyond prototype stage conceptually. The roadmap should focus on:
1. hardening,
2. protocol centralization,
3. campaign intelligence,
4. multi-module governance,
5. multi-site scaling.

---

# Phase OAS-1 — Stabilization and contract hardening
**Target horizon:** 0–8 weeks

## Goals
- make OAS the stable foundation for all other modules
- formalize contracts for campaign orchestration
- improve reliability, observability, and test coverage
- standardize tool/module registration

## Deliverables
- campaign schema registry
- module adapter interface for Parallax / OAE / OPAD / DAMD
- improved contract tests for:
  - handoff
  - campaign transitions
  - event emissions
  - budget and approval rules
- cost ledger with real token and compute attribution
- command center cleanup and restart/recovery fixes

## Technical work
- normalize campaign step definitions
- add module capability registry
- enforce typed responses from downstream modules
- introduce retry / fallback / compensation policies per task type
- expand backend and frontend test coverage
- add better session continuation for interrupted campaigns

## Success criteria
- old and new projects can be resumed safely
- each downstream component can register itself as a routable capability
- cost and model usage is visible per campaign

---

# Phase OAS-2 — Darklab protocol hub
**Target horizon:** months 2–4

## Goals
- make OAS the canonical owner of Darklab workflow semantics
- introduce unified campaign objects and shared provenance keys
- support structured routing across knowledge, simulation, lab, and compute tasks

## Deliverables
- Research Intent Package (RIP)
- Knowledge Artifact (KA)
- Simulation Intent Package (SIP)
- Experiment Intent Package (EIP)
- Run Record (RR) ingest path
- Compute Request / Compute Receipt contracts
- campaign state machine v1

## Technical work
- define shared Pydantic models or equivalent typed schemas
- create schema versioning policy
- build event normalization layer
- store per-campaign provenance graph
- add confidence and evidence scoring fields to campaign records

## Success criteria
- OAS can track one campaign across multiple modules with stable IDs
- downstream artifacts become queryable by campaign, stage, and evidence type
- campaign replay is possible

---

# Phase OAS-3 — Campaign intelligence and decision engine
**Target horizon:** months 4–7

## Goals
- upgrade OAS from router to research decision engine
- let OAS choose the next step based on confidence, cost, risk, and readiness
- reduce unnecessary simulation and physical execution

## Deliverables
- decision policy engine
- readiness scoring:
  - knowledge readiness
  - simulation readiness
  - experiment readiness
  - infrastructure readiness
- next-step recommendation engine
- uncertainty-aware routing rules

## Technical work
- add decision heuristics for:
  - stay in Parallax
  - move to OAE
  - move to OPAD
  - escalate to human approval
- integrate model selection with task value and budget
- add campaign reflection layer after each stage
- add stop conditions and “insufficient evidence” paths

## Success criteria
- OAS can explain why it routed a campaign to a specific module
- campaign cost is reduced through better stage selection
- users see clear decision checkpoints rather than black-box routing

---

# Phase OAS-4 — Governance, memory, and audit maturity
**Target horizon:** months 7–12

## Goals
- make OAS suitable for serious scientific operations
- deepen memory and provenance
- support approval, authorship, and safety rules across modules

## Deliverables
- three-layer memory:
  - episodic
  - semantic
  - reflective
- approval policy engine
- authorship and artifact provenance model
- audit export bundle for a campaign
- alerting and intervention queue

## Technical work
- persistent campaign journal
- reusable template library for common campaign types
- human approval records with digital signatures
- artifact lineage graph
- cost / evidence / version snapshots per iteration

## Success criteria
- any completed campaign can be audited
- memory can improve future campaigns without contaminating provenance
- approvals and overrides are preserved as first-class records

---

# Phase OAS-5 — Multi-node and multi-site orchestration
**Target horizon:** months 12–18

## Goals
- make OAS the orchestrator for distributed Darklab deployments
- coordinate local cluster devices, remote compute, and physical labs
- manage load, latency, and partial failure

## Deliverables
- resource-aware scheduler
- node capability discovery
- queueing and priority model
- failure isolation and degraded-mode execution
- site-aware routing for:
  - local research node
  - simulation node
  - physical lab node
  - DAMD compute node

## Technical work
- distributed task queue
- node health heartbeat and lease model
- policy for local-first vs remote-first execution
- compute affinity and data locality logic
- multi-site dashboard

## Success criteria
- campaigns can run partially across multiple nodes
- partial outages do not collapse the entire workflow
- OAS can schedule based on both capability and governance constraints

---

# Phase OAS-6 — External platformization
**Target horizon:** months 18+

## Goals
- make OAS usable as a platform service
- support external partners, teams, and workflows
- expose stable APIs and modular deployment

## Deliverables
- API and webhook layer
- RBAC and tenant separation
- campaign templates for external users
- partner-facing console
- SDK / CLI for creating and managing campaigns

## Success criteria
- OAS can coordinate internal and external Darklab campaigns
- users can launch campaigns programmatically
- OAS becomes the product backbone of Darklab

---

## OAS KPI suggestions

### Reliability
- campaign completion rate
- resume success rate
- failure recovery rate

### Efficiency
- cost per campaign
- cost per useful artifact
- model routing efficiency
- human intervention frequency

### Intelligence
- correctness of next-step recommendations
- reduction in unnecessary module invocations
- improved campaign throughput over time

### Governance
- percentage of campaigns with complete provenance
- percentage of high-risk actions gated correctly
- audit replay success rate

---

## OAS dependency map

### Upstream
- user intent
- API or UI campaign creation
- memory stores
- model providers

### Downstream
- Parallax
- OAE
- OPAD
- DAMD

### Critical interfaces
- campaign schemas
- event bus
- cost ledger
- approval records
- node registry

---

## Recommended first milestone

The most important near-term OAS milestone is:

**“One command center, one campaign object, one provenance graph.”**

Until that exists, the rest of Darklab will remain partially fragmented.
