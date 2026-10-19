<!--
DRAFT CONTENT FOR THE GOOGLE DOC (issue #20). Not the final document.
The final, team-editable version lives in Google Docs. This file only carries the text so it can be
built into the Google Doc in a later session (see the memory note "report-google-doc").

Markers:
  [[TEAM: ...]]    something only the team knows (names, index numbers, screenshots, dates)
  [[FIGURE n: ...]] a figure to insert; the Mermaid source is named next to it
  [[CHECK: ...]]   a fact to confirm before submission
-->

# COVER PAGE

University of Moratuwa
Department of Computer Science and Engineering

Software Process Management

**Scrum Agents Workbench**
A Multi-Agent CASE Workbench for Scrum Practice

Group Project Report

Group members

| Name | Index number | Workstream |
|---|---|---|
| Isurumuni Wijesooriya | | Foundation, orchestrator, documentation, live-run fixes, UI |
| Kavee Ranathunga | | Product Owner, Scrum Master and QA agents |
| Sandali Jayawardhana | | Developer agent, REST API and event stream, frontend |
| Madhawa Abhayawickrama | | DevOps agent, end-to-end test |
| Himadree | | Architect agent, process model and lecture concepts |
| Pasindu Senevirathne (L0rd008) | | Metrics, traceability, retrospective loop, release step, demo |

Submitted to: Course lecturer, Software Process Management
Date of submission: 20 October 2026
Repository: https://github.com/Muniya-64bit/scrum-agents-workbench

---

# Abstract

The assignment asked for a multi-agent computer-aided software engineering (CASE) workbench in
which agents interact to complete the full software development life cycle (SDLC) under the Scrum
methodology. We built the Scrum Agents Workbench. A human gives it a product idea, and six agents
built on large language models (LLMs) take that idea through the SDLC in sprints, each agent
playing a Scrum role: Product Owner, Scrum Master, Architect, Developer, QA and DevOps. Together
they produce a product backlog with non-functional requirements, an architecture and API contract,
working code with tests, bug reports and fixes, and a versioned release for every sprint. A human
approves or rejects the two Scrum ceremonies that need judgement, sprint planning and sprint
review.

The workbench treats the Scrum process itself as a managed software process, following the
concepts of the Software Process Management module. The process is held as an explicit model,
with activities, roles, product flow, entry and exit criteria and a responsibility matrix, and the
orchestrator is driven by that model. Every action is written to an append-only event log, from
which a descriptive model of the process actually followed can be rebuilt. The process is measured
with Goal-Question-Metric (GQM), and each sprint closes a Plan-Do-Check-Act cycle in which the
retrospective changes the process for the next sprint.

The system has a REST API, a web interface, record and replay of LLM answers, and a scripted
three-sprint demonstration. It has 305 automated backend tests at 98.7% line coverage, and 132
frontend tests. In the demonstration the retrospective's process changes raise
commitment reliability from 70% to 100% and first-pass test yield from 50% to 100%. Live runs on a
local 14-billion-parameter model complete the whole process but do not yet deliver working
stories. We report this as a limitation of model quality, not of the process.

---

# Table of contents

[[Insert the automatic table of contents in Google Docs: Insert > Table of contents]]

---

# 1. Introduction

## 1.1 Background

Software is built by people following a process, whether that process is written down or not. In
Lecture 1 a software process was defined as "a structured set of activities required to develop a
software system", with four activities that every process contains: specification, design and
implementation, validation, and evolution. Managing a process means monitoring and controlling those
activities. Lecture 1 also listed the problems seen when the process is not managed: open-ended
requirements, uncontrolled change, arbitrary schedules and insufficient test time.

Scrum is one widely used answer. It is an iterative and incremental framework in which a
cross-functional team delivers a working increment at the end of each short, time-boxed sprint, and
inspects and adapts both the product and the process at fixed events.

Computer-aided software engineering (CASE) tools support parts of this work: requirements tools,
modelling tools, test tools. With LLMs a tool can now go further and *perform* activities, not only
record them. That is the setting of this assignment.

## 1.2 The assignment

> Design and develop a Multi-agent CASE workbench for Scrum Practice. Agents should interact and
> complete the work from end-to-end SDLC scope under scrum methodology.

We read three requirements in this sentence:

1. **Multi-agent.** Several agents with distinct roles, not one model doing everything.
2. **Interaction.** The agents depend on each other's work products: the Developer builds what the
   Product Owner specified and the Architect designed, and QA tests it and sends bugs back.
3. **End-to-end SDLC under Scrum.** From an idea to a released increment, organised as Scrum
   sprints with Scrum's roles, events and artifacts.

## 1.3 Objectives

- O1. Automate every SDLC activity, from requirements to release, with role-based agents.
- O2. Organise the work as Scrum: backlog, sprint planning, execution, review, retrospective,
  several sprints, and a human in the decisions that need judgement.
- O3. Make the process explicit, measurable and improvable, applying the module's process
  management concepts rather than only automating tasks.
- O4. Make every result traceable and reproducible: from story to design, code, test and release,
  and from any metric back to the events that produced it.
- O5. Build it as a team using Scrum ourselves.

## 1.4 Structure of this report

Section 2 summarises the background concepts we used from the module. Section 3 states the
workbench's requirements. Section 4 describes the design and Section 5 the implementation. Section
6 evaluates the system. Section 7 describes how we ran the project with Scrum. Section 8 concludes.

---

# 2. Background: process concepts applied

This section lists the module concepts that shaped the design and where each one appears. The
details follow in Sections 4 and 5.

| Lecture | Concept | Where it is applied in the workbench |
|---|---|---|
| 1 | Software process as a structured set of activities; specification, design and implementation, validation, evolution | The six phases and six agents cover all four activities (Table 4.1) |
| 2 | Functional and non-functional requirements; user stories in agile methods; requirements validation | User stories with Given/When/Then acceptance criteria; measurable NFRs; rule-based backlog check |
| 3 | Process vs project; team-oriented development; goals of process modelling | Process model kept separate from each project run; agents coordinated through shared work products |
| 4 | Elements of a process model: activities, product flow, control flow, roles, agents; process scripts and process programs; principles | `process_model.py` (activities, product flow, roles, RACI); prompts as process scripts, orchestrator as process program; Scrum principles |
| 5 | Prescriptive and descriptive process models; iterative enhancement model | Prescribed process levers vs the process recorded in each sprint's event; every sprint is one increment |
| 6 | Spiral model and Incremental Commitment Spiral Model; Unified Process | Alternatives we considered; human gates as commitment reviews |
| 7 | Engineering process models; XP; ISO/IEC 12207 | Test-first practice as a process lever; mapping to 12207 process groups |
| 8 | Process handbooks and electronic process guides; quality gates in process deployment | Generated process handbook; web UI as a process guide; approval gates |
| 9–10 | Descriptive process modelling; model analysis (completeness, consistency) | Event log as a descriptive model; backlog and criteria checks |
| 11 | Process modelling languages, MVP-L, entry and exit criteria; prescriptive vs proscriptive | Entry and exit criteria per activity, checked and reported but not enforced |
| 12 | Process improvement: CMMI, PDCA, QIP, GQM, Experience Factory | GQM metrics, PDCA view per sprint, QIP mapping, maturity self-assessment |

## 2.1 Process, process model and process agent

Lecture 4 defines a process model as a description of activities, the product flow between them
(which work products each activity consumes and produces), the control flow (the order in which
they run), the refinement of activities and the roles that perform them. It separates *process
enactment*, performed by a human, from *process execution*, performed by a machine, and calls the
performer a *process agent*. It separates a *process script*, a description interpreted by
humans, from a *process program*, a description interpreted by machines.

These distinctions fit an LLM workbench closely. Our agents are process agents in the lecture's
sense. Each agent's prompt is a process script: natural-language instructions that the model
interprets, much as a person reads a procedure. The orchestrator and the process model are a
process program, code that decides which activity runs next and checks its conditions. The human
at the gates is a second, human process agent.

## 2.2 Prescriptive and descriptive models

Lecture 5 contrasts prescriptive models (how work *should* be done) with descriptive models (how
work *is* done), and describes the improvement cycle between them. The current process is
described, problems are found and fixed in a prescriptive model, and once the change is adopted
the model becomes descriptive again. Our workbench keeps both. The process levers for a sprint are
prescriptive, and the configuration actually recorded when the sprint was planned is descriptive.
The retrospective closes the cycle.

## 2.3 Lifecycle models

Lecture 5 presents the iterative enhancement model of Basili and Turner: build a properly chosen
part of the system, then add functionality in iterations, each completed in a waterfall-like way
and integrated with the existing system. It names Scrum as one of the modern models that follow
this pattern. Every sprint in the workbench runs a small waterfall (design, code, test, release)
for the chosen stories and integrates the result into the same repository, tagged `v0.1.0`,
`v0.2.0` and so on.

## 2.4 Measurement and improvement

Lecture 12 presents model-based improvement (CMMI, SPICE) and continuous improvement (PDCA, QIP,
Kaizen, Six Sigma), Goal-Question-Metric as the way to define measurements top-down from goals,
and the Experience Factory as the way to keep what a project learned. We used GQM to define the
metrics, PDCA and QIP to structure the sprint loop, and the CMMI levels for a self-assessment
(Section 6.6).

---

# 3. Requirements

## 3.1 Functional requirements

| ID | The workbench shall... |
|---|---|
| FR1 | accept a product idea and create a project from it |
| FR2 | produce a product vision, epics and user stories with acceptance criteria and estimates (Product Owner) |
| FR3 | produce non-functional requirements with a measurable target |
| FR4 | produce an architecture, diagrams and an API contract before the first sprint (Architect) |
| FR5 | plan each sprint within a capacity, with a sprint goal and tasks per story (Scrum Master) |
| FR6 | implement each sprint story as code in a version-controlled workspace (Developer) |
| FR7 | write tests from the acceptance criteria, run them and report bugs (QA) |
| FR8 | send bugs back to the Developer and retest, up to a retry limit |
| FR9 | hold a sprint review and a retrospective, and change the process for the next sprint |
| FR10 | produce a versioned release for each sprint (DevOps) |
| FR11 | run several sprints until the backlog is done or a sprint limit is reached |
| FR12 | stop for human approval at sprint planning and sprint review, and act on a rejection |
| FR13 | trace every story to its design, code, tests and release |
| FR14 | measure the process with defined metrics and show them per sprint |
| FR15 | show the work live: backlog, sprint board, activity feed, approvals |

## 3.2 Non-functional requirements

Following Lecture 2, each NFR is stated with a measure so that it can be verified.

| ID | Category | Requirement | Measure |
|---|---|---|---|
| NFR1 | Product (reliability) | Invalid LLM output shall not corrupt project state. | Every agent output is validated against a schema; invalid output is retried, never written |
| NFR2 | Product (reproducibility) | A run shall be reproducible without calling a model. | A recorded scenario replays with 0 fallbacks and 0 prompt drifts |
| NFR3 | Organisational (cost) | Development and CI shall not spend tokens. | Mock mode is the default; CI makes 0 LLM calls |
| NFR4 | Organisational (quality) | The code base shall stay tested. | CI fails below 95% line coverage |
| NFR5 | Product (auditability) | Every change of state shall be recorded. | Agents change state only through the Tools API, which writes one event per call |
| NFR6 | Product (safety) | Agent-written files shall stay inside the project's workspace. | Absolute paths, `..` and `.git` are rejected and logged |
| NFR7 | Product (portability) | The system shall run on one laptop with no external services in mock mode. | SQLite, no Docker needed; setup with `make setup` |

## 3.3 Scope and assumptions

The generated products are small web APIs (Python, FastAPI and SQLite), so that the agents' code
can be tested automatically. The workbench runs locally, with no authentication. LLM answers come
from Claude (Anthropic) or a local model through Ollama.

---

# 4. Design

## 4.1 Overview

[[FIGURE 1: System architecture. Mermaid source: README.md, "System architecture"]]

The workbench has six parts:

| Component | Responsibility |
|---|---|
| Web UI (React, Vite) | Projects, backlog, sprint board, activity feed, approval inbox, metrics, traceability |
| REST API (FastAPI) | HTTP interface and a Server-Sent Events stream of the event log |
| Orchestrator | The Scrum state machine: which phase runs next, which agents run in it, where to stop for a human |
| Agents | One per Scrum role; each turns project state into a prompt and applies the validated answer |
| Tools API | The only way agents change state; every call writes an event |
| LLM client | Calls the model, validates JSON against a schema, retries, caches; mock, live, record and replay modes |

All state is in one SQLite database, and each project's generated code is in its own git
repository (the workspace).

## 4.2 Agents and Scrum roles

Scrum has three accountabilities: Product Owner, Scrum Master and Developers. We kept the first
two as agents and split the Developers into four specialists, so that each SDLC activity has a
clear owner (Lecture 4: "a role is a set of processes belonging together").

**Table 4.1: Agents, Scrum roles and SDLC activities**

| Agent | Scrum role | SDLC activity (Lecture 1) | Consumes | Produces |
|---|---|---|---|---|
| Product Owner | Product Owner | Specification | Product idea | Vision, epics, user stories with acceptance criteria, NFRs |
| Scrum Master | Scrum Master | Process management | Backlog, process levers, last retro's actions | Sprint goal, sprint backlog, tasks, stand-up, retrospective, process changes |
| Architect | Developer | Design | Backlog, NFRs | Architecture, diagrams, API contract per story |
| Developer | Developer | Implementation | Story, design, contract, open bugs | Code committed per story, bug fixes |
| QA | Developer | Validation | Acceptance criteria, contract, code | Tests, test runs, bug reports |
| DevOps | Developer | Release (evolution) | Code, tests, retrospective | Dockerfile, CI workflow, release notes, version tag |

## 4.3 How the agents interact

The agents never call each other through free text. They interact through shared work products in
the database and the workspace (the product flow of Lecture 4), and in two places through direct
calls:

- **The bug loop.** QA runs the tests. For each failure it files a bug and calls the Developer
  with that story; the Developer fixes and commits; QA tests again. A bug the Developer marks fixed
  that still fails is reopened. After the sprint's retry limit the bug stays open for a human.
- **Test-first.** When the process lever `test_first` is on, the Developer asks QA to write the
  tests before it codes, and is then told to make those tests pass.

[[FIGURE 2: One sprint, step by step (sequence diagram). Mermaid source: README.md, "One sprint, step by step"]]

The Architect, Developer and QA are also bound by a shared **API contract**. For every story the
Architect designs the endpoints (method, path, request fields, success and error statuses). The
Developer must implement exactly that contract. QA writes its tests against it and checks the
code's routes against it by rule.

## 4.4 The Scrum state machine

[[FIGURE 3: State machine. Mermaid source: docs/process-handbook.md, "Control flow"]]

A project moves through `idea → backlog → sprint_planning → execution → review → retro → release`.
After a release it returns to sprint planning while stories are left and fewer than `MAX_SPRINTS`
sprints have run; otherwise it ends at `done`. Sprint planning and sprint review are gates: the run
stops until the human approves or rejects.

- **Rejecting a sprint plan** returns its stories to the backlog and removes the tasks the plan
  created. The Scrum Master then plans the same sprint again, and its prompt includes the human's
  reason.
- **Rejecting a review** does not repeat the sprint. The retrospective is given the reason and must
  respond to it.

These gates are the quality gates of Lecture 8 and the stakeholder commitment reviews of the
Incremental Commitment Spiral Model (Lecture 6): points where a human decides, on evidence,
whether to commit to the next step.

## 4.5 The process model

The process is not hard-coded in the orchestrator. It is held as data in `process_model.py`, with
one *activity* per phase, and each activity carries the elements of a process model from Lecture 4:

- purpose and name;
- the responsible role and the agents that perform it;
- product flow: the work products it consumes and produces;
- entry and exit criteria, as in MVP-L's `entry_criteria` and `exit_criteria` (Lecture 11);
- whether a human gate follows it;
- one row of a responsibility assignment matrix (RACI).

The orchestrator reads from this model which agents run in a phase and which phases are gated. The
same model is served at `GET /process/model` and generates the tables of the process handbook
(Section 4.8).

**Table 4.2: Responsibility assignment matrix (R responsible, A accountable, C consulted, I informed)**

| Activity | Human | PO | SM | Architect | Developer | QA | DevOps |
|---|---|---|---|---|---|---|---|
| Requirements and sprint-0 design | C | R/A | I | R | I | I | I |
| Sprint planning | A | C | R | I | C | C | I |
| Sprint execution | I | C | C | R | R/A | R | I |
| Sprint review | A | C | R | I | I | I | I |
| Sprint retrospective | I | C | R/A | C | C | C | C |
| Release | I | I | I | I | C | C | R/A |

**Table 4.3: Entry and exit criteria**

| Activity | Entry criteria | Exit criteria |
|---|---|---|
| Requirements and sprint-0 design | The project has a product idea | The backlog has at least one story; every story has acceptance criteria; a sprint-0 architecture exists |
| Sprint planning | The backlog has stories not yet in a sprint | The sprint has at least one story; every sprint story has tasks; committed points do not exceed the capacity |
| Sprint execution | An active sprint has at least one story | Every sprint story has tests; no sprint story has an open bug; every sprint story is done (the Definition of Done) |
| Sprint review | A sprint has been planned | A burndown snapshot is recorded |
| Sprint retrospective | A sprint has been planned | The retrospective is saved |
| Release | The sprint's retrospective is saved | A release is recorded for the sprint |

**Prescriptive or proscriptive.** Lecture 11 distinguishes a prescriptive process language, which
forces the performer through the steps, from a proscriptive one, which guides but leaves freedom.
Our criteria are proscriptive. They are checked at every phase and the result is logged and shown
at the gate, but an unmet criterion does not stop the run. An LLM team will not always meet the
Definition of Done, and when it doesn't, the process should carry the unfinished story into the
next sprint rather than halt. The human, who sees the unmet criteria at the gate, makes the
decision.

## 4.6 Requirements engineering in the workbench

Lecture 2 describes the requirements engineering process as elicitation, analysis, validation and
management, and notes that agile methods express requirements as user stories.

- **Elicitation and specification.** The Product Owner turns the idea into a vision, epics and
  stories in the form "As a *role*, I want *goal*, so that *benefit*". Each story has
  acceptance criteria in Given/When/Then form, a priority and a story-point estimate.
- **Non-functional requirements.** Lecture 2 warns that a goal such as "easy to use" cannot be
  verified, and that an NFR needs a measure. The Product Owner therefore writes 2 to 4 NFRs, each
  with a category (product, organisational, external, as in Lecture 2's classification), a "shall"
  sentence and a measurable target. The Architect must name the design decision that meets each one.
- **Validation.** A rule-based backlog check, with no LLM call, runs after the Product Owner. It
  applies Lecture 2's quality properties (complete, consistent, unambiguous) and Lecture 10's
  model-analysis ideas (completeness and consistency analysis):

| Rule | Lecture basis |
|---|---|
| A story has no acceptance criteria | Completeness: not testable |
| A criterion is not in Given/When/Then form | Structured specification |
| The role, goal or benefit is missing | Completeness |
| Two stories have the same title | Consistency (duplicate or conflicting requirements) |
| Points are off the 1, 2, 3, 5, 8, 13 scale, or above 8 | Estimation discipline; split large stories |
| Vague words (fast, easy, simple, user-friendly, ...) | Requirements imprecision |
| An NFR has no number in its measure | Goal vs verifiable NFR |

- **Management.** Every story is traced to the artifacts that satisfy it (Section 4.7). Unfinished
  stories return to the backlog and are planned first in the next sprint.

## 4.7 Traceability

Lecture 5 gives "traceability between requirements and components" as an example of what a
lifecycle model demands without prescribing how. We implement it with trace links from each story
to its design, its code files, its test files and the release that shipped it. The Traceability
page shows a story → design → code → test → release table and marks every gap. Two metrics measure
it: trace completeness (stories with design, code and tests) and acceptance-criteria coverage
(test functions per criterion).

## 4.8 Process documentation: handbook and guide

Lecture 8 recommends keeping one process model and generating the handbooks for each audience from
it, so that the documents cannot disagree. Our `docs/process-handbook.md` follows the lecture's
outline: introduction (purpose, audience, specifics, applicability, relationship to other models,
version), definitions, process views, references and appendices (templates, checklists,
tailoring). Its tables of activities, product flow, RACI and criteria are generated from the
process model, and a test fails if the handbook and the model drift apart.

The web UI plays the part of the electronic process guide described in the same lecture. It shows
each performer where the process is, what is waiting for them, and the work products of every
activity.

## 4.9 Measuring the process: GQM

Following Lecture 12, the metrics were defined top-down: goals first, then questions, then metrics.

**Table 4.4: GQM model**

| Goal | Question | Metrics |
|---|---|---|
| G1 Improve the predictability of sprint delivery (Scrum Master) | Q1 How much of what we commit do we deliver? | Committed and completed points, commitment reliability, carried-over stories |
| | Q2 Is the sprint on track while it runs? | Burndown against an ideal line |
| G2 Improve product quality (QA) | Q3 Does new code pass its tests the first time? | First-pass yield, test pass rate, test runs |
| | Q4 How many defects appear and how costly are they to fix? | Bugs reported, open at the end, fix attempts, retry-limit hits, invalid LLM outputs |
| G3 Keep requirements traceable (Product Owner) | Q5 Is every story covered by design, code and tests? | Trace completeness, acceptance-criteria coverage |
| G4 Control the cost of the AI team | Q6 What does the AI team cost per unit of delivered work? | LLM calls, tokens, estimated cost, cost per completed point |

Every metric is computed by replaying the append-only event log, so any number can be traced back
to the events that produced it.

## 4.10 Improving the process: PDCA and QIP

Each sprint is one Plan-Do-Check-Act cycle (Lecture 12):

- **Plan:** sprint planning with the current process levers;
- **Do:** execution by the Architect, Developer and QA;
- **Check:** the review and the sprint's GQM metrics;
- **Act:** the retrospective proposes typed process changes, and the next sprint is planned with them.

[[FIGURE 4: PDCA loop. Mermaid source: docs/architecture.md, "Process improvement loop"]]

The retrospective can change four levers, each within fixed bounds:

| Lever | Range | Typical trigger |
|---|---|---|
| Capacity | 3 to 40 points | The team delivered less than it committed ("yesterday's weather") |
| Fix retries | 1 to 5 | A bug reached the retry limit |
| Test-first | on or off | Defects escaped into testing (XP's test-first practice, Lecture 7) |
| Working agreements | at most 5 | A practice worth keeping; added to every agent's prompt |

The same loop maps onto the Quality Improvement Paradigm:

| QIP step | In the workbench |
|---|---|
| Characterise | Backlog, design and the metrics of earlier sprints |
| Set goals | GQM goals G1 to G4 |
| Choose process | The process levers for the sprint |
| Execute | Sprint planning, execution, review |
| Analyse | Sprint metrics and the retrospective |
| Package | The changes stored with the retrospective and recorded in the next sprint's plan |

## 4.11 Design decisions

| Decision | Reason | Alternative considered |
|---|---|---|
| Agents change state only through a Tools API that logs every call | One audit trail, a descriptive record of the process, and no free text written into the database | Agents writing to the database directly |
| Every agent answer is validated against a schema and retried if invalid | An LLM's mistakes are caught before they corrupt state | Parsing free text |
| The process model is data, read by the orchestrator | One definition serves the orchestrator, the API and the handbook | Phase logic hard-coded in the orchestrator |
| Proscriptive criteria | An imperfect AI team should carry work over rather than stop | Blocking entry and exit criteria |
| Human gates at planning and review only | These are the two Scrum events that need a stakeholder's judgement | A gate after every phase (slow), or none (no control) |
| Mock, record and replay LLM modes | Free and deterministic development, CI and demos | Live calls only |
| SQLite and a git workspace per project | No setup, and the generated code has real history | A database server and containers |
| Scrum on an iterative enhancement base | Small increments suit LLM agents that make mistakes; each sprint is checked and released | Waterfall (one big risky pass); Spiral/ICSM, whose explicit risk analysis is heavier than a few-sprint project needs; Unified Process, too heavy in artifacts |

---

# 5. Implementation

## 5.1 Technology

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy, SQLite, pydantic |
| LLM | Anthropic Claude (default `claude-sonnet-5-5`), or a local model through Ollama; model selectable per role |
| Generated products | Python, FastAPI, sqlite3, pytest, in a git repository per project |
| Frontend | React 19, TypeScript, Vite |
| Quality | pytest with coverage, ruff, Vitest, Playwright for the demo video, GitHub Actions CI |

Size: about 9,200 lines of application code (backend and frontend) and 5,800 lines of tests.

## 5.2 Code structure

```
workbench/
  api/            REST API and event stream
  agents/         BaseAgent, Tools API, one module per agent, registry
  orchestrator/   Scrum state machine
  db/             data model and queries
  llm/            LLM client: validation, retries, cache, modes, providers
  process.py      process levers and the retrospective's changes
  process_model.py  activities, product flow, criteria, RACI
  requirements.py NFR storage and the backlog check
  metrics.py      GQM metrics replayed from the event log
  contract.py     the Architect's API contract and the rule-based check
frontend/         web UI
tests/            backend tests
demo/scenarios/   the scripted demonstration
```

## 5.3 The agent framework

Every agent subclasses `BaseAgent` and supplies four things: a system prompt, an output schema, a
method that builds the prompt from the project state, and a method that applies the validated
output through the Tools API. `BaseAgent.run` does the rest:

1. logs `agent_started`;
2. builds the prompt and appends the team's working agreements from the last retrospective;
3. calls the LLM client, which validates the answer against the schema and retries with the
   validation error if it is invalid;
4. applies the output through the Tools API;
5. logs `agent_finished` with the tokens used, the duration and the model.

Agents are registered by role in one dictionary, so a new agent does not touch the orchestrator.
Agents with several duties (the Scrum Master plans, reviews and runs the retrospective; the
Architect designs at sprint 0 and per story) delegate to one handler per phase.

## 5.4 The agents

**Product Owner.** One call turns the idea into a vision, 2 to 4 epics and 6 to 10 stories, each
with at least two acceptance criteria, a priority and points, plus the NFRs. The schema requires at
least two criteria per story, so a short answer is retried. The backlog check runs afterwards.

**Architect.** At sprint 0 it writes an architecture overview (technology, components, key
decisions with reasons), three Mermaid diagrams (components, data model, main flow) and an OpenAPI
specification, all traced to the whole backlog. For each sprint story it writes a design delta
with that story's endpoints. The runtime is fixed in its prompt (Python, FastAPI, sqlite3): in one
live run the model chose Node.js and MongoDB, and nothing built after that worked.

**Scrum Master.** Planning: picks stories within the capacity, carried-over stories first, and
creates two to four tasks per story. The LLM proposes and the code decides: unknown story ids and
anything over capacity are dropped. Review: a stand-up style summary and a burndown snapshot.
Retrospective: what went well and wrong, actions, and typed process changes, given the sprint's
metrics and a rule-based advisor's suggestion. Unfinished stories go back to the backlog.

**Developer.** One call and one commit per story, with the story, its criteria, the architecture,
the design and contract, open bugs and the current files. It returns the full content of each
changed file. Unsafe paths are rejected. For bug fixes it counts attempts per bug.

**QA.** Writes pytest files from the acceptance criteria and the contract, runs them in a
subprocess with a time limit, checks the routes against the contract, files one bug per failure,
and drives the fix loop. If a test fails because of the test code itself (an import error, a
`NameError`), QA rewrites its own tests rather than blaming the Developer.

**DevOps and release.** Writes a Dockerfile, a CI workflow and release notes. The notes list only
stories whose tasks are all done. The release step tags the workspace (`v0.N.0`) and traces the
release to its stories.

## 5.5 Orchestration

`Orchestrator.step` moves a project to its next phase. It logs the phase start, checks and logs the
entry criteria, runs the phase's agents in order, checks and logs the exit criteria, and, at a
gate, waits for approval. `approve` records the human's decision. A rejected plan triggers the
reset described in Section 4.4. `run_to_end` approves every gate automatically and is used for
tests and the demo.

## 5.6 LLM client

The client hides the model behind one call, `complete_json(system, prompt, schema)`, and provides:

- **Validation and retries.** The answer must parse as the schema; otherwise the error is sent back
  to the model.
- **Response cache.** Identical calls are answered from the cache.
- **Four modes.** `mock` returns canned answers (development and CI, no cost); `live` calls the
  model; `record` calls the model and saves each answer; `replay` answers from the saved files.
  Recordings are keyed by meaning (role, handler, phase, sprint, story), not by the prompt text,
  so editing a prompt does not invalidate a recording. A changed prompt is reported as drift.
- **Providers.** Anthropic, or Ollama for local models, with the JSON schema passed as the
  required output format.
- **Per-role models**, for example a code-specialised model for the Developer and QA.

## 5.7 Data and events

The data model has projects, epics, stories, sprints, tasks, bugs, artifacts, trace links and
events.

[[FIGURE 5: Data model (ER diagram). Mermaid source: README.md, "Data model"]]

The event log is append-only and is the system's memory. It feeds the live activity feed (over
Server-Sent Events), every metric and the descriptive record of the process. The process levers,
the NFRs and the backlog check are stored in event payloads rather than new tables, so the schema
did not change as the process gained features.

## 5.8 Web interface

[[TEAM: screenshots of each page]]

| Page | What it shows |
|---|---|
| Projects | All projects and their phase; create a project from an idea |
| Backlog | Vision, NFRs, the backlog check's warnings, epics and stories with criteria |
| Board | The sprint's tasks in To do, In progress, Testing and Done columns |
| Activity | The live event feed, filterable by agent |
| Inbox | What is waiting for approval, with Approve and Reject (with a reason) |
| Metrics | GQM metrics per sprint, burndown, velocity, cost, one PDCA card per sprint |
| Traceability | Story → design → code → test → release, with gaps marked |

A phase bar on every page shows where the project is and offers the next step.

## 5.9 Testing and CI

The backend has unit tests per agent, tests of the state machine, the metrics, the API, the LLM
modes and the workspace safety rules, and end-to-end tests that run a whole project. Tests run in
mock mode with a temporary database and workspace. CI runs ruff, the backend tests with a 95%
coverage gate, and the frontend typecheck, tests and build on every pull request.

---

# 6. Evaluation

## 6.1 Requirements coverage

| Requirement | Met | Evidence |
|---|---|---|
| FR1–FR4 | Yes | Backlog phase: vision, stories, NFRs, architecture, contract |
| FR5 | Yes | Planning within capacity; carried-over stories first |
| FR6–FR8 | Yes | Code per story; tests from criteria; bug loop with retry limit |
| FR9 | Yes | Retrospective changes the levers (demo: capacity 10→7, test-first on) |
| FR10–FR11 | Yes | Three sprints, `v0.1.0` to `v0.3.0` in the demo |
| FR12 | Yes | Gates; rejecting a plan re-plans the sprint |
| FR13–FR15 | Yes | Traceability page and metrics; live UI |
| NFR1 | Yes | Schema validation with retries on every call |
| NFR2 | Yes | Demo replay: 0 fallbacks, 0 drifts |
| NFR3–NFR4 | Yes | CI in mock mode; 98.7% coverage against a 95% gate |
| NFR5–NFR7 | Yes | Tools API events; path checks; runs on one laptop |

## 6.2 Automated tests

| Suite | Tests | Result in CI (Linux) |
|---|---|---|
| Backend (pytest) | 305 | all pass; 98.7% line coverage (gate 95%) |
| Frontend (Vitest) | 132 | all pass; typecheck and build pass |
| Lint (ruff) | | clean |

On a Windows laptop two backend tests fail. QA recognises an application error by looking for
`app/…py` in the traceback, and Windows writes that path with backslashes. This is a portability
defect we still have to fix. Two time-sensitive frontend tests are also flaky on a slow machine.

## 6.3 Scripted demonstration: the process improves itself

The `todo-app` scenario replays hand-written LLM answers. Everything else is real: the orchestrator,
the agents' logic, the generated FastAPI code, the pytest runs, the git tags and the metrics. The
two defects in it are real code that really fails.

| Sprint | Committed | Completed | Commitment reliability | First-pass yield | Bugs | Process used |
|---|---|---|---|---|---|---|
| 1 | 10 | 7 | 70% | 50% | 2 | capacity 10, 1 fix retry, test-first off |
| 2 | 6 | 6 | 100% | 100% | 0 | capacity 7, 2 fix retries, test-first on |
| 3 | 3 | 3 | 100% | 100% | 0 | capacity 7, 2 fix retries, test-first on |

What happens:

- In sprint 1, QA's tests catch a missing empty-title check, and the Developer fixes it. The delete
  story is still wrong after the one allowed fix, so the execution exit criteria report
  `no_open_bugs` and `stories_done` as unmet. The story is carried over.
- The retrospective reads the metrics (70% reliability, defects escaped into testing, a bug at the
  retry limit) and changes the process: capacity 7 (yesterday's weather), test-first on, two fix
  attempts, and a working agreement to write the acceptance tests first.
- Sprints 2 and 3 run with the changed process, and every story passes its tests the first time.
- The generated application ends with 14 passing tests, and the backlog check reports no warnings
  on the six stories.

This is the PDCA cycle working as designed. It is also a scripted scenario, so it demonstrates the
mechanism, not the quality of a live model.

[[TEAM: screenshot of the Metrics page PDCA cards and the burndown]]

## 6.4 Live runs

The team ran the workbench live on a local model (`qwen2.5:14b`, and `qwen2.5-coder:14b` for the
Developer and QA, through Ollama on an RTX 4070 Ti SUPER) with a "library lending" idea. These runs
found real pipeline defects, which were fixed:

| Defect found | Fix |
|---|---|
| QA wrote tests to `/tests/...`; absolute paths were rejected, so no test was ever saved | Leading slash read as the repository root |
| Stories had one acceptance criterion | The schema requires at least two; short answers are retried |
| The Architect chose Node.js and MongoDB | The runtime is fixed in the prompts |
| The Developer's rewrite dropped earlier routes | Prompt rule to keep what other stories use |
| Test-code errors were filed as application bugs | QA rewrites its own broken tests |
| A binary SQLite file crashed the prompt builder | Binary files are skipped |

After these fixes, five consecutive live runs completed every phase to `done`, with the contract
check, test rewriting and the fix loop all working. They still delivered **0 story points**: the
generated code had errors such as a missing table or a 404 instead of 201, and every bug reached
its retry limit. The process ran as designed, and the retrospectives correctly reported the
failures. The remaining gap is in the code a 14B local model writes. A run with a stronger model
is the obvious next test.

## 6.5 Evaluating our process model as a process modelling notation

Lecture 11 gives requirements for process modelling notations and a +/O/− scale (full, partial,
none). We applied them to our own process model (`process_model.py` with the event log and the
levers):

| Requirement | Rating | Reason |
|---|---|---|
| R1 Natural representation | + | Activities, roles, work products and criteria map one-to-one to Scrum terms |
| R2 Support of measurement | + | GQM metrics are defined on the event log of the modelled activities |
| R3 Tailorability | O | Four levers tailor each sprint; activities and criteria change only by editing code |
| R4 Formality | O | Criteria are executable checks; the control flow is code, not a formal semantics |
| R5 Comprehensibility | + | A generated handbook and the UI present the model to people |
| R6 Execution and enactment | + | The orchestrator executes the model; agents and the human enact it |
| Flexibility (on-the-fly change) | O | The process changes between sprints, not during one |
| Traceability | + | Every event is linked to its phase, agent and work products |

## 6.6 Maturity self-assessment (CMMI)

Using the CMMI maturity levels of Lecture 12 as a lens on the *AI team's* process:

- **Level 2, Managed.** Requirements are managed and traced, sprints are planned and tracked, work
  products are under version control, and every run is measured. Met.
- **Level 3, Defined.** The process is defined once (the process model and handbook), and every
  project follows it, tailored within defined bounds by the levers. Largely met.
- **Level 4, Quantitatively managed.** Metrics exist and the retrospective acts on them, but a
  handful of sprints is far too little data for statistical process control. Not met.
- **Level 5, Optimising.** The PDCA loop is a step towards continuous improvement, but changes are
  local to one project. There is no organisation-wide experience base (Lecture 12's Experience
  Factory). Not met.

## 6.7 Mapping to ISO/IEC 12207

| 12207 process group (Lecture 7) | Covered by |
|---|---|
| Agreement processes | Not covered: the human is the only stakeholder |
| Project processes (planning, control, measurement, risk) | Scrum Master, metrics, gates. Risk management is not explicit |
| Technical processes (requirements to maintenance) | Product Owner, Architect, Developer, QA, DevOps |
| Software support processes (documentation, configuration management, QA, verification, review) | Generated docs, git per project, QA agent, contract check, reviews at the gates |
| Reuse processes | Not covered |

## 6.8 Limitations

- Live runs complete the process but do not yet deliver working stories with a local 14B model
  (Section 6.4). No end-to-end run with Claude has been made yet.
- Two backend tests fail on Windows because of a path-separator assumption (Section 6.2).
- Generated products are restricted to small Python and FastAPI web APIs.
- Generated code runs in a plain directory, not a container. That protects against accidents, not
  against hostile code.
- No authentication: the workbench is for local use.
- Risk is not managed explicitly (no risk register, unlike the spiral model).
- Lessons stay inside one project. A new project starts from the default process.
- A handful of sprints gives little data, so the retrospective's changes rest on small samples.

---

# 7. Project management: how we used Scrum

We built the workbench with the same method it automates. The product backlog was a set of GitHub
issues, each sprint was one day, and every change went through a reviewed pull request.

## 7.1 Team and workstreams

The work was split into six workstreams, labelled `ws1` to `ws6` on the issues, so that members
could build in parallel against the shared contracts agreed on day 1.

| Workstream | Scope | Members (pull requests) |
|---|---|---|
| WS1 Orchestrator | Foundation, state machine, docs; later local-model runs, agent quality, UI restyle | Isurumuni Wijesooriya (#22–#25, #43–#47) |
| WS2 PO and SM agents | Product Owner, Scrum Master | Kavee Ranathunga (#26, #27) |
| WS3 Architect and Developer agents | Architect, Developer | Himadree (#28), Sandali Jayawardhana (#31) |
| WS4 QA and DevOps agents | QA, DevOps, end-to-end test | Kavee Ranathunga (#33), Madhawa Abhayawickrama (#35, #36) |
| WS5 Backend and data | REST API, event stream | Sandali Jayawardhana (#30) |
| WS6 Frontend | Shell, board, activity feed, inbox | Sandali Jayawardhana (#32, #34) |
| Day 3 integration | Metrics, traceability, retro loop, release step, test suite, demo | Pasindu Senevirathne (#37, #38) |
| Lecture concepts | Process model, NFRs, backlog check, gate rejection, handbook | Himadree (#42) |

Scrum roles in the team: Isurumuni Wijesooriya acted as Product Owner and maintainer (issues,
reviews, merges). The Scrum Master role rotated by day, and everyone else worked as a developer
on their workstream.

## 7.2 Sprints

| Sprint | Goal | Issues | Outcome |
|---|---|---|---|
| Day 1 (14 Oct): foundation | Repository, architecture and contracts, database, LLM wrapper, base agent, orchestrator | #1–#6 | Done. Merged in PR #22; onboarding and docs in #23–#25 |
| Day 2 (15–16 Oct): build | Six agents, REST API and event stream, frontend shell, activity feed and inbox | #7–#15 | Done except DevOps, which slipped to day 3. PRs #26–#34 |
| Day 3 (17 Oct): finish | End-to-end integration, metrics and traceability, retro loop and release, tests and demo | #16–#19, #39, #40 | Done. PRs #35–#38; the demo plays three sprints |
| Hardening (18–20 Oct) | Lecture concepts, live runs on a local model, agent quality, UI, report | #41, #20, #21 | PRs #42–#47 merged; report in progress |

Commits per day on `main` (excluding merges): 14 Oct 4, 15 Oct 4, 16 Oct 11, 17 Oct 44, 18 Oct 4,
19 Oct 10. The peak on day 3 is the integration work.

[[FIGURE 6: GitHub Project board at the end of each day (screenshots)]]

## 7.3 Artifacts and events we used

| Scrum element | How we did it |
|---|---|
| Product backlog | GitHub issues, labelled by day (`day-1` to `day-3`) and workstream (`ws1` to `ws6`) |
| Sprint backlog and board | GitHub Project board "Scrum Agents Workbench", one column per status |
| Sprint planning | Start of each day: pick the day's issues and assign them by workstream |
| Daily stand-up | Short written stand-up (done, doing, blocked), logged in `docs/scrum/standups.md` |
| Definition of Done | Pull request reviewed by one teammate; CI green (lint, tests, 95% coverage, frontend build); docs updated |
| Sprint review | Demo of the merged increment at the end of each day |
| Retrospective | 15 minutes at the end of each day, logged in `docs/scrum/retrospectives.md` |

## 7.4 Stand-ups

**Day 1 (14 Oct)**

| Member | Done | Doing | Blocked |
|---|---|---|---|
| Isurumuni Wijesooriya | Repo tooling, architecture doc, DB schema, LLM wrapper, BaseAgent, orchestrator (PR #22) | README quickstart, agent registry, stand-up and retro templates | Team needs to review and merge #22 before agent work |
| Kavee Ranathunga | Read the contracts and the BaseAgent example | Planning the Product Owner and Scrum Master agents | Waiting for #22 |
| Sandali Jayawardhana | Set up the local environment | Planning the API endpoints and the frontend shell | Waiting for #22 |
| Himadree | Set up the local environment, reviewed the schema | Planning the Architect's outputs (overview, diagrams, OpenAPI) | Waiting for #22 |
| Madhawa Abhayawickrama | Set up the local environment | Planning the DevOps agent | Waiting for #22 |
| Pasindu Senevirathne | Reviewed #22 | Planning metrics and traceability | None |

**Day 2 (15–16 Oct)**

| Member | Done | Doing | Blocked |
|---|---|---|---|
| Isurumuni Wijesooriya | Documentation overhaul (architecture, API, agents, development guide) | Reviewing agent PRs | None |
| Kavee Ranathunga | Product Owner agent (#26); Scrum Master agent with planning, stand-up and retro (#27) | QA agent: tests from acceptance criteria, bug loop | None |
| Sandali Jayawardhana | REST API and SSE stream (#30), Developer agent (#31) | Frontend shell, board, activity feed, inbox (#32, #34) | None |
| Himadree | Architect agent: sprint-0 design and per-story design delta (#28) | Documenting the Architect | None |
| Madhawa Abhayawickrama | Started the DevOps agent | Dockerfile, CI workflow and release notes | Needs the Developer and QA agents to test against |
| Pasindu Senevirathne | Designed the GQM goals and metrics | Metrics engine from event replay | Needs agents to log their usage |

**Day 3 (17 Oct)**

| Member | Done | Doing | Blocked |
|---|---|---|---|
| Isurumuni Wijesooriya | Reviewed and merged day-2 PRs | Reviewing integration PRs | None |
| Kavee Ranathunga | QA agent with pytest runner and fix loop (#33) | Fixing QA's leftover `.pyc` files | None |
| Sandali Jayawardhana | Frontend shell, activity feed and approval inbox | UI fixes after integration | None |
| Himadree | Architect docs | Reviewing the end-to-end flow | None |
| Madhawa Abhayawickrama | DevOps agent (#35) | Full workflow end-to-end test (#36) | None |
| Pasindu Senevirathne | Metrics engine, Metrics and Traceability pages | Retro levers, release step, record/replay, demo scenario and video (#38) | Two integration bugs found (#39, #40), fixed the same day |

## 7.5 Retrospectives

**Sprint 1 (Day 1: foundation)**
- Goal achieved? Yes: contracts, schema, LLM wrapper, base agent and orchestrator merged (#1–#6).
- Went well: we agreed the shared contracts first (agent output schemas, the Tools API, the agent
  registry), so each workstream could build without touching the others' code.
- Didn't go well: one large foundation PR blocked everyone until it was reviewed.
- Actions: smaller PRs; review within the same morning; each member starts from the `BaseAgent`
  example.
- Metrics: 6 issues planned, 6 done; 4 PRs merged (#22–#25).

**Sprint 2 (Day 2: agents, API, UI)**
- Goal achieved? Mostly: five agents, the API and the UI shell were merged; DevOps moved to day 3.
- Went well: mock mode let every agent be built and tested without an API key or token cost, and
  the agent registry meant no merge conflicts in the orchestrator.
- Didn't go well: the agents were tested alone, not together, so integration problems were still
  unknown, and the documentation fell behind the code.
- Actions: run the whole flow end to end first thing on day 3 (#16); update docs in the same PR as
  the code.
- Metrics: 9 issues planned, 8 done; 9 PRs merged (#26–#34).

**Sprint 3 (Day 3: integration, metrics, demo)**
- Goal achieved? Yes: the full flow runs from idea to release over several sprints, with metrics,
  traceability, the retrospective loop and a scripted demo.
- Went well: the end-to-end test caught integration bugs (#39, #40), which were fixed the same
  day, and the coverage gate kept quality up on a very busy day.
- Didn't go well: integration was left to the last day (44 of the commits are on 17 Oct), and the
  agents had only run in mock mode, never against a live model.
- Actions: run the workbench on a live model (done on 19 Oct; it found and fixed six pipeline
  defects, Section 6.4); bring the module's process concepts into the tool (#41); write the report
  (#20).
- Metrics: 6 issues planned, 6 done; 4 PRs merged (#35–#38).

## 7.6 Development workflow

Every change starts from an issue and is built on a branch named `feat/<issue>-<name>`. It is
merged through a pull request with one review and green CI (CONTRIBUTING.md). This is our own
Definition of Done, and it mirrors what the workbench asks of its agents.

---

# 8. Conclusion

We built a multi-agent CASE workbench in which six LLM agents, each in a Scrum role, take a product
idea through the whole SDLC in sprints. They interact through shared work products, a shared API
contract and a test-and-fix loop, and a human approves or rejects the two ceremonies that need
judgement.

The main contribution is treating the Scrum process as a managed software process, as the module
teaches, not only automating tasks. The process is an explicit model with activities, roles,
product flow, entry and exit criteria and a RACI matrix. That model drives the orchestrator and
generates the process handbook. The event log keeps a descriptive record of what actually happened.
GQM metrics measure the process, and every sprint ends with a retrospective that changes it. In the
demonstration this loop measurably improves delivery.

The honest limit is model quality. The process runs end to end live, but a local 14B model does not
yet write code that passes its own tests.

**Future work:**
- a reference run with a stronger model, and patch-based code edits so a rewrite cannot drop
  existing routes;
- an explicit risk register reviewed at each retrospective (Lecture 6);
- an experience base that carries working agreements to new projects (Lecture 12's Experience
  Factory);
- a daily stand-up during execution, not only at the review;
- containerised execution of generated code.

---

# References

1. Software Process Management, lecture notes 1–12, University of Moratuwa.
2. K. Schwaber and J. Sutherland, *The Scrum Guide*, 2020.
3. I. Sommerville, *Software Engineering*, 9th/10th ed. (requirements engineering, Lecture 2).
4. V. R. Basili and A. J. Turner, "Iterative Enhancement: A Practical Technique for Software
   Development", *IEEE Trans. Software Engineering*, 1975.
5. B. Boehm, "A Spiral Model of Software Development and Enhancement", *IEEE Computer*, 1988.
6. H. D. Rombach, "MVP-L: A Language for Process Modeling In-the-Large", 1991.
7. V. R. Basili, G. Caldiera and H. D. Rombach, "The Goal Question Metric Approach", 1994.
8. V. R. Basili, "The Experience Factory and its Relationship to Other Improvement Paradigms", 1993.
9. ISO/IEC 12207:2008, *Systems and software engineering — Software life cycle processes*.
10. CMMI Product Team, *CMMI for Development, Version 1.3*, 2010.
11. Project repository and documentation: https://github.com/Muniya-64bit/scrum-agents-workbench

---

# Appendices

## Appendix A. Running the workbench

```
make setup && make test && make run     # API on :8000 (mock mode)
make ui-setup && make ui                # web UI on :5173
python scripts/demo.py run --scenario todo-app --fresh   # scripted three-sprint demo
```

## Appendix B. API summary

[[Insert the endpoint table from README.md, section "API"]]

## Appendix C. Process handbook

[[Insert, or link, docs/process-handbook.md]]

## Appendix D. Agent output schemas

[[Optional: the pydantic models in workbench/schemas.py]]
