# Laurel: Requirements

Laurel is a conversational assistant that gives every student one front door to university life. It knows who you are, shows you what needs your attention before you ask, answers from your own data with a source on every reply, and takes action for you once you say yes. Laurel takes the admin out of the way so students can get back to learning. It was built for the CSIT hackathon, under the theme *Innovating Education: make education smarter, easier and more enjoyable.*

This document is the source of truth for scope, rules and demo. Requirement IDs (FR, NFR, US, D) are stable. Code, tests and scenarios refer to them.

## 1. The problem

A student's everyday experience of university is spread across a dozen disconnected systems, each with its own login, layout and vocabulary:

- the learning management system (Canvas) for due dates, submissions and marks
- the handbook for programs, courses, prerequisites and majors
- the class timetable
- the enrolment system
- the fees and payments portal
- the academic calendar of census dates, drop deadlines, breaks, exams and results
- the library, room booking, print credit, the IT service desk and the careers board

Simple questions take real effort to answer:

- *What's due this week, and did I actually submit it?*
- *Can I fit this course around my job?*
- *If I drop this class now, do I still pay for it?*
- *What do I still need for my minor?*
- *Who do I even email about this?*

The answers exist, but they are split across systems. Help desks keep office hours, and the questions come up at 11pm. The cost is more than lost time:

- deadlines get missed
- the wrong class gets dropped after census
- a timetable clash only shows up in week one
- small anxieties pile up

The friction falls hardest on the students with the least slack: first-years who don't know the vocabulary yet, international students working in a second language, and anyone fitting study around work, caring or commuting.

Every hour spent hunting through portals, or recovering from a missed deadline, is an hour not spent learning. And none of these systems tells a student what they've forgotten: they only answer the questions students already know to ask.

## 2. The idea: one front door that gets admin out of the way

Laurel replaces "which system do I need, and where in it?" with a single conversation, and starts that conversation for you: the moment you open it, it shows what needs your attention this week.

| Theme | How Laurel delivers it |
| --- | --- |
| **Smarter** | Proactive, personal and grounded. Before you type anything, *Coming up* lists what's overdue, what's due soon, holds, library books and the next key dates, most urgent first. Laurel already knows the logged-in student's program, results, enrolments, fees and holds, so it answers *their* question rather than giving generic advice. Every fact comes from a tool call over the university's data and ends with a source line. It never comes from the model's memory. |
| **Easier** | Answers and actions in one place. Laurel plans your study week around your classes and commitments, with a free study room for each session. It checks a timetable against your commitments, builds a semester-by-semester plan, enrols you, drops a class, books a study room, renews library loans or logs an IT ticket. Anything that changes something is shown to you first and only happens after a clear yes. |
| **More enjoyable** | It lives where students already are: a chat bubble on the university's own web pages (through a Chrome extension), a full web app, and a CLI. It suggests questions to try, makes waiting feel friendly, and lets you peek behind the curtain at the tools it used. |

When Laurel can't help, because the question is out of scope or the data doesn't have the answer, it says so plainly. It names the right team and, if you'd like, drafts the email for you to send. It never guesses.

## 3. Who it's for

The demo accounts are real-feeling personas, not test fixtures. Each password is the same as the username.

| Persona | Login | What Laurel does for them |
| --- | --- | --- |
| New domestic student with fixed weekday commitments | `demo1` | Finds classes that fit around a 9-to-5 week, plans every semester to graduation, and enrols with confirmation |
| New full-time, full-fee student who can't attend Tuesdays | `demo2` | Builds a two-semester plan with no Tuesday workshops, and explains upfront fees |
| New international student | `demo3` | Explains international fees, and hands visa and study-load questions to the right office instead of guessing |
| Full-time student juggling four classes | `demo4` | Shows the deadlines coming up across all four classes, Data Mining's due Sunday night first, before any are overdue, the moment they open Laurel, plans study sessions with free rooms to get them done, and covers marks, print credit, IT tickets and internships |
| Student who failed a course | `demo5` | Gives honest GPA and WAM numbers and shows what the fail means for their plan |
| Final-semester student | `demo6` | Shows what's left to graduate, and handles library loans and renewal |
| Student with an overdue balance and hold | `demo7` | Explains the hold, what it blocks and what is owed |
| Student already enrolled for next term | `demo8` | Checks the consequences of dropping a class and drops it with confirmation |
| Students on larger degrees with majors and minors | `demo9` to `demo14` | Compares programs and tracks progress towards a named major or minor |

## 4. How Laurel meets the judging criteria

| Criterion | What in Laurel addresses it | Where it shows in the demo |
| --- | --- | --- |
| **Problem relevance** | Built around questions students really ask, across ten everyday domains. It covers the moments that cost students most (deadlines, census and drop dates, clashes, holds), not just FAQs, and turns them into time back for learning. | Personas in section 3. Each demo beat starts from a real student question. |
| **Desirability and impact** | It tells you what's coming up before you ask, so nothing is missed, then helps you get it done. No new app to learn. It sits on the pages students already visit, knows who they are without asking, works 24/7, and *does* things instead of linking to them. Nobody is left stuck: out-of-scope questions get a ready-to-send draft to the right team. | *Coming up* appearing the moment the widget opens. A study plan for the week with rooms, and one booked. The handoff draft. |
| **Solution and creativity** | Proactive rather than reactive: *Coming up* is computed straight from the tools with no model call, so it is instant, and each item is a ready-made question. The study-week planner joins coursework, the timetable and room booking into a plan to learn by. Underneath, a tool-calling agent over the university's own systems, not a document-search chatbot. Every fact is an exact lookup with a source line. Every action uses a check-then-confirm pattern enforced in code. Identity is wired through the login, so the model can never reach another student's record. A mock enrolment service with a live dashboard shows real API calls as they happen. | The trace toggle under a reply. The live dashboard lighting up during an enrolment. A refused probe for another student's results. |
| **UI/UX** | A home screen that starts with what matters, where one click asks about it. Clean chat in the university's own colours. Suggested questions change with the page you're on. A lively loading indicator, per-message copy, thumbs and retry, and an expand button. Plans and timetables come back as tables. Mobile-safe input. The widget hands off to the full web app already signed in. | Clicking a suggestion chip, expanding the widget, then opening the full web app. |
| **Functionality** | 30 tools across 10 domains, a fixed-seed synthetic dataset with a validator, unit tests for every tool, and a scenario runner that asks the live agent scripted questions and reports pass rates. | Everything in the demo is live, not mocked screenshots. |
| **Presentation** | A four-minute storyline (section 12.1) built on four live turns, following one student with two deadlines this Sunday, with traces making the invisible visible. A recorded video backs up the live demo. | Section 12.1. |

## 5. Hard rules (do not violate)

1. **No scraping** of university sites, no calls to real university systems, and no real credentials or student IDs.
2. **All data is synthetic**, seeded from public program pages. Every record carries `provenance` (`from_public_page` or `synthetic`). Only values listed in section 11 are `from_public_page`.
3. **Never state** a course, code, session, date, mark or number that is not in the data. If it is missing, say so and offer a handoff (FR-15). The one exception is general study suggestions for an assignment, given only on request and always labelled as general suggestions rather than course materials (FR-35).
4. **No state-changing tool call without explicit student confirmation** in the same conversation: enrolling, dropping or booking a room (FR-10, NFR-04).
5. Every simulated action carries a **simulation notice** that also says the data is synthetic (FR-16).
6. **Draft, never send.** Laurel never sends a message on the student's behalf (FR-14).
7. **Only the logged-in student's information.** Tools read the student number from the run context, never from an argument the model supplies. No tool lists, searches or returns another student. Without a login, tools return `{"found": false}`.
8. Keep code comments concise.

## 6. Approach and stack

### 6.1 Tool calling, not RAG

Laurel is a **tool-calling agent**, not a document-search system. A foundation model reads the student's message against a fixed instruction set. It decides which Python function to call and with what arguments, gets a structured JSON result back, and writes the reply from that result, citing the source. Every lookup is exact and deterministic over small JSON files, with no embeddings or similarity search. The goal is the same as RAG's (answers grounded in real data rather than model memory), but the mechanism is more precise, and it lets Laurel *act* as well as answer.

```
 student ──► widget on a uni page / web app / CLI
                │  message + run context {student_number}  (set by the login, never by the model)
                ▼
     IBM watsonx Orchestrate ──► Laurel agent (instructions + 30 tools + model)
                │                        │ picks a tool, fills its arguments
                ▼                        ▼
     Python tools (tools/*_tools.py) ──► data/*.json, or the mock enrolment service (mockapi/)
                │
                ▼
     JSON result (facts + "source" block) ──► reply with a Source: line
```

### 6.2 Layers

- **Data.** `data/*.json` is generated deterministically by `seed/generate.py` from public facts and checked by `seed/validate.py`.
- **Tools.** `tools/*.py` holds plain Python functions decorated with `@tool`. Each one loads data through a cached `tools/common.py:load`, does an exact lookup or computation, and returns a dict with a `source` block. The docstring is what the model sees when it chooses a tool.
- **Identity.** A `context: AgentRun` parameter gives the tool `context.request_context["student_number"]`, set from the authenticated session. The model never sees or supplies it, so it cannot be asked or tricked into fetching someone else's data.
- **Programs are data, not code.** `data/programs.json` models each program as stages of ordered items (`course`, `options`, `choice`). `tools/programs.py` resolves the student's program, so adding a degree is a data change.
- **The confirmation pattern.** Every action that changes something is split into a `check_*` tool with no side effects and a paired action tool. The action tool refuses unless it gets a matching `check_id` and `student_confirmed: true`. The agent must show a summary and wait for a clear yes on the *next* message.
- **The human safety net.** `draft_enquiry` is what Laurel calls instead of guessing. It picks the right team from `contacts.json` and returns only that team at first, so Laurel asks whether the student wants a draft; the email is written only on a yes (`include_draft`), or straight away when the student already asked to be put in touch. Nothing is sent.
- **Interfaces.** All three share the same session and chat-client code:
  - a React web app (`frontend/`, served by `webapp/`)
  - a floating chat widget for university pages (`widget/`), delivered by a Chrome extension (`extension/`)
  - a CLI (`planner/`)
- **Optional live service.** `mockapi/` is a FastAPI stand-in for a real enrolment system, with in-memory state and a live dashboard of every request (section 6.5).

### 6.3 Stack

- Python 3.12 and `ibm-watsonx-orchestrate` (the `orchestrate` CLI and the `@tool` decorator), pinned to the tested version. The `planner` client uses the ADK's `RunClient` and `ThreadsClient`.
- Agent: `agents/study_planner.yaml` (`spec_version: v1`, `kind: native`), on the `watsonx-orchestrate/frontier` model. It chose the right tool more reliably than the trial's default model, and it refused other-student probes every time.
- Packaging: `scripts/build_package.py` assembles `build/package` (tools and data, never `accounts.json`). `scripts/deploy.py` imports every tool and the agent, retries transient errors and detects an expired login.
- Web: FastAPI and uvicorn for `webapp/` and `mockapi/`. React with Vite (plain JavaScript) for `frontend/` and `widget/`.
- Portability: tool logic is plain functions, so the same tools could be driven from another agent runtime if needed.

### 6.4 Tool contracts

All tools are stateless and return JSON-serialisable dicts. Every successful response includes:

```json
"source": {"provenance": "from_public_page|synthetic|mixed", "snapshot_date": "YYYY-MM-DD", "file": "courses.json"}
```

When something is not found, a tool returns `{"found": false, "reason": "..."}`. Tool descriptions say plainly when to use the tool and what it returns.

| Domain | Tools | Reqs |
| --- | --- | --- |
| Know me | `get_student_profile`, `get_academic_record` | FR-18, FR-20 |
| Program and courses | `lookup_program`, `lookup_course`, `get_major_minor_progress` | FR-01 to FR-03, FR-26 |
| Timetable and plans | `get_timetable`, `check_availability_fit`, `find_courses_that_fit`, `build_plan` | FR-04 to FR-08 |
| Enrol and drop | `check_enrolment`, `submit_enrolment`, `list_enrolments`, `check_drop`, `drop_enrolment` | FR-09 to FR-13, FR-24, FR-25 |
| Dates | `get_current_week`, `get_key_dates`, `get_term_dates` | FR-22, FR-23 |
| Money | `get_fees` | FR-21 |
| Coursework (Canvas) | `list_assignments` | FR-27, FR-35 |
| Study spaces | `check_room_availability`, `book_room` | FR-28 |
| Campus services | `get_print_balance`, `create_it_ticket`, `check_it_ticket_status`, `search_internships` | FR-29 |
| Library | `get_current_loans`, `renew_loans` | FR-30 |
| Coming up | `get_my_week`, `plan_study_week` | FR-33, FR-34 |
| Human handoff | `draft_enquiry` | FR-14, FR-15 |

**Availability** is parsed by `tools/scheduling.py`. The format is `{"busy": [{"days": ["Mon","Tue","Wed","Thu","Fri"], "start": "09:00", "end": "17:00"}]}`. A workshop option is `fits` if it overlaps no busy block, `clashes` if it does, and `unknown` if its time is missing. Lectures are assumed online with recordings, so they are never compared. A course can be attended if at least one open workshop option fits. When the student has given no availability, tools assume none and say so.

**Plans** (`tools/planning.py`) place each course in the earliest term that:
- comes after its prerequisites
- has a fitting, open workshop
- keeps the term within the semester's credit-point load
- keeps the program's stage order

Workshops in the same term must not overlap. Option credit points are filled with suggestions the student can swap. Anything without a confirmed fitting time is flagged as unconfirmed.

**Enrolment** (`tools/enrolment.py`):
- `check_enrolment` reports prerequisites, seats, clashes with availability and with other classes, holds, and already enrolled or passed. It returns a deterministic `check_id` and changes nothing.
- `submit_enrolment` refuses unless `student_confirmed` is true and the `check_id` matches.
- Success returns a `SIM-` reference.
- Errors are coded: `INVALID_SELECTION`, `ENROLMENT_CLOSED`, `ACCOUNT_HOLD`, `PREREQUISITE_NOT_MET`, `ALREADY_ENROLLED`, `ALREADY_PASSED`, `CLASS_FULL`, `TIMETABLE_CLASH`, `NOT_CONFIRMED` and `INVALID_CHECK`. Each comes with a plain-language message, and full or closed classes get alternatives.

**Dropping** (`tools/dropping.py`) follows the same two steps, using the census date and the published last day to drop:

| When | Outcome |
| --- | --- |
| Before census | Can drop. The fee is avoided. |
| From census to the last day to drop | Can drop. The fee still applies. |
| After the deadline, or the term has ended | Refused with `DROP_DEADLINE_PASSED`, plus a draft to Student Connect |
| Not enrolled in that course | `NOT_ENROLLED` |

Laurel quotes the tool's consequences message, so the fee and the dates are never worked out by the model.

**Coming up** (`tools/week_tools.py`) reads the other tools' results rather than the data files, so the rules for overdue, renewable and holds live in one place. Items are ordered action, overdue, today, soon, upcoming, then the study-plan suggestion. It covers holds and balances, unsubmitted assignments (recently overdue, due this week, and the next due date), loans overdue or due within 7 days, and key dates within 28 days.

**Study-week plans** (`tools/study_week.py`) cover the next seven days with two-hour slots (09–11, 11–13, 14–16, 16–18, 19–21), at most two a day. They skip the student's workshops and any stated busy times. Overdue work gets two sessions first, work due within the week gets two before its due date, and later work gets one to make a start. Each session gets the first room free in the bookings data. Nothing is booked; booking a room goes through the usual confirmation.

**Room booking** follows the same check-then-confirm pattern. **Print balance, IT tickets, internship search and library renewal** are harmless or reversible, so Laurel acts straight away.

### 6.5 Mock enrolment service (`mockapi/`)

An optional HTTPS service that stands in for the university's enrolment system. The demo shows a real API being called, and every call can be watched as it happens.

- It reuses the enrolment and drop logic in `tools/` and adds memory. Enrolling takes a seat and adds the course to the student's list. Dropping frees the seat. A repeat enrolment is `ALREADY_ENROLLED`.
- Endpoints need an `X-API-Key` header: check, enrol, list, drop-check and drop under `/v1/`, plus `/admin/` endpoints for the event stream, state and reset.
- The dashboard shows every request (method, path, student, status, timing and result), coloured by status, with filters and the full JSON on click. It also shows the enrolments held and the seats taken.
- `python -m mockapi --tunnel --deploy` starts the service and a free Cloudflare tunnel, then redeploys the enrolment tools to call it.
- If the service is configured but unreachable, the tools say so, change nothing and give no reference. They never fall back silently.

### 6.6 Repository layout

```
.
├── agents/study_planner.yaml   # Laurel's instructions, tool list and model
├── data/                       # generated synthetic data (programs, courses, timetable, students, fees,
│                               #   key dates, Canvas, study spaces, library, print, careers, contacts)
├── seed/                       # public facts, fixed-seed generator, validator and its stored report
├── tools/                      # @tool functions by domain, plus shared logic (scheduling, planning,
│                               #   enrolment, dropping, studyspaces, programs, common)
├── planner/                    # CLI login and chat client, and the scenario runner
├── webapp/                     # FastAPI backend: sessions, chat, profile, widget auth, static hosting
├── frontend/                   # React web app: login, chat, profile
├── widget/                     # floating chat widget (Vite library build) and smoke tests
├── extension/                  # Chrome extension that puts the widget on the university's site
├── demo/                       # widget host pages for development and an offline fallback
├── mockapi/                    # mock enrolment service and live dashboard
├── scripts/                    # package, deploy, widget stub, page capture
├── tests/                      # unit tests per domain, scripted scenarios and recorded results
└── docs/                       # this file, widget integration, example questions
```

## 7. Capabilities by domain

| Epic | A student can… |
| --- | --- |
| **Know me** | Be greeted by name. See their status, load, enrolments and holds. Get results, GPA and WAM computed from their record. |
| **Plan my study** | Ask about any program or course by name, code or handbook code. Check whether a course fits their week. Find courses that do fit. Get a semester-by-semester plan to graduation. Ask what a major or minor still needs. |
| **Act for me** | Enrol and drop with check-then-confirm. Book a study room. Renew library loans. Log an IT ticket. |
| **See my week** | Open Laurel and see what's overdue, what's due soon, holds, library books and upcoming key dates, then ask about any of them in one click. Get study sessions for the week planned around classes and commitments, each with a free room. |
| **Stay on top** | Ask what week it is and when the break, exams, results, census and deadlines are. Ask what's due this week, whether something was submitted, and what mark they got. |
| **Money and services** | Get fees for their fee type and how to pay. Check balance and holds, print credit and internships open to their program. |
| **Human safety net** | Out-of-scope or unanswerable questions get a plain "I can't help with that", the right team named, and a draft email to send themselves. |

## 8. Functional requirements

| ID | Requirement | Stories | Priority |
| --- | --- | --- | --- |
| FR-01 | Answer questions about a program's structure (stages, compulsory courses, options, majors, minors, credit points, duration) from the program data | US-01, US-02 | Must |
| FR-02 | Look up a course by title, handbook code or timetable code, and return one consolidated record. Ask which one when several match | US-03 | Must |
| FR-03 | A course record includes credit points, description, delivery mode, assumed knowledge, prerequisites and coordinator where available, and names what is missing | US-03, US-04 | Must |
| FR-04 | Use the student's stated commitments (busy times) when checking timetables and building plans. Assume none when none were given and say so, and accept corrections at any time | US-05 | Must |
| FR-05 | Return a course's components (lecture, workshop) and each option's day, time, mode, campus, class number and seats | US-06 | Must |
| FR-06 | Label each workshop option `fits`, `clashes` or `unknown` against the student's busy times, and say whether the course can be attended. Find the courses in a term that fit | US-06 | Must |
| FR-07 | Generate a semester-by-semester plan covering every remaining requirement at the student's load, state the total duration, and flag unconfirmed items | US-07 | Must |
| FR-08 | Regenerate the plan when the load, busy times or preferred options change | US-08 | Should |
| FR-09 | An enrolment check reports prerequisites, seats, clashes, holds and duplicates, and changes nothing | US-09 | Must |
| FR-10 | Enrolment is submitted only after explicit confirmation in the same conversation, verified in code by `check_id` and `student_confirmed` | US-10, US-11 | Must |
| FR-11 | Simulated enrolment returns a reference number or a coded error | US-11, US-12 | Must |
| FR-12 | Translate each error code into plain language with a next step or an alternative | US-12 | Should |
| FR-13 | List the student's enrolments on request | US-13 | Could |
| FR-14 | Draft an enquiry for the right team, and never send it | US-14 | Should |
| FR-15 | Every factual answer names its source, snapshot date and provenance. Missing or out-of-scope questions get a plain "I don't have that" and a handoff | US-15, US-16 | Must |
| FR-16 | Every simulated action carries a visible simulation notice. The tool calls behind each answer can be viewed (trace) | US-17, US-18 | Must |
| FR-17 | Every data record carries `provenance`, and the agent uses it when stating sources | US-15, US-17 | Must |
| FR-18 | A profile tool returns only the logged-in student's profile: status, load, start term, residency, fee type, enrolments and hold | US-19 | Must |
| FR-19 | Login checks a username and password against hashed demo accounts and starts a session for one student. Every message carries that student's number in the run context | US-20 | Must |
| FR-20 | An academic record tool returns results, credit points passed, GPA (0 to 4) and WAM to one decimal | US-21 | Must |
| FR-21 | A fees tool explains the student's fee type and payment options, estimates fees for chosen courses, and reports balance, due date and holds. Answers differ by fee type | US-22 | Should |
| FR-22 | A term calendar tool returns start, enrolment, census and payment dates, and marks which are published | US-23 | Should |
| FR-23 | Key-date tools answer what week it is, breaks, exam periods, results release, census, add, drop and withdraw deadlines and holidays, with days to go and the date used | US-24 | Must |
| FR-24 | Drop tools show whether the student can drop, the fee outcome and the census and drop dates. They drop only after confirmation and refuse after the deadline | US-25 | Should |
| FR-25 | An optional mock enrolment service handles check, enrol, list and drop over HTTPS with memory and a live dashboard. When it is unreachable, the tools say so and change nothing | US-26, US-27 | Should |
| FR-26 | Support several programs. Tools default to the student's own program and can be asked about another. Report what a named major or minor still needs | US-28, US-29, US-30 | Should |
| FR-27 | A Canvas tool lists the student's assignments with due dates, submission status and marks, including "due this week". Each has a descriptive title ("Assignment 1: Data Pre-processing") and a one-sentence summary, given when the student asks about that assignment | US-31 | …to know what's due and whether I submitted it | Should | "What's due this week" lists this week's items by descriptive title. Submission status and marks match `canvas.json`. An unsubmitted item has no mark. Asking about one assignment gives its summary |
| FR-28 | Study-room tools show free rooms by date, time and building, and book one only after confirmation | US-32 | Should |
| FR-29 | Campus-service tools report print credit, raise and check IT tickets, and search internships open to the student's program | US-33 | Could |
| FR-30 | Library tools list current loans and due dates, and renew one or all loans, explaining any refusal (holds, renewal limit) | US-34 | Could |
| FR-31 | A web app offers login, chat with a trace toggle, and a profile page. It recovers the conversation after a reload | US-35 | Must |
| FR-32 | A chat widget runs on the university's web pages through a Chrome extension (or a saved-page fallback). It offers page-aware suggested questions and opens the full web app already signed in | US-36 | Should |
| FR-33 | A *Coming up* summary lists, most urgent first (covering the next few weeks, not just this one), holds and balances, overdue and upcoming assignments, library loans due or overdue, and key dates within four weeks, each with a follow-up question. The web app shows it on opening and the widget as a collapsed bar with a count that expands to every item, without a model call. Once a conversation starts it stays one click away, as a header button with the item count that opens the full list | US-37 | Must |
| FR-34 | A study-week planner suggests sessions for the next seven days for unsubmitted assignments, overdue first, around the student's workshops and stated busy times, each with a free study room. It books nothing | US-38 | Should |
| US-39 | …help getting started on an assignment | Should | After the summary I'm asked whether I want study resources. A yes gets concepts to review, an approach and kinds of resources, clearly labelled general and not from the course, with no made-up links, then an offer to plan sessions or book a room |
| FR-35 | Asked about one specific assignment, the agent gives its summary and offers study resources. On a yes it gives general study suggestions from the model's own knowledge (concepts, approach, kinds of resources), labelled as not course materials, with no invented links, pages or lecture weeks, then offers to plan study sessions or book a room | US-39 | Should |

## 9. Non-functional requirements

| ID | Requirement | Check |
| --- | --- | --- |
| NFR-01 | Accuracy: answers match the data, and the agent never states anything absent from it | The 10 scripted questions in `python -m planner.scenarios --tag nfr01 --repeat 3`. Target: at least 9 of 10 correct with a source |
| NFR-02 | Responsiveness: a typical answer in about 10 to 20 seconds, with a loading indicator throughout | Observed in testing |
| NFR-03 | Privacy: no real student number, credential or personal data. Names and emails are fictional. Passwords are stored only as salted hashes | Review of the data files, and validator checks |
| NFR-04 | Safety: no state-changing call without prior explicit confirmation | Tool-call traces for D3, D8 and D11 |
| NFR-05 | Recoverability: agent, tools and data are text files in version control | Repository contents |
| NFR-06 | Clarity: plain English, with tables for plans and timetables | Demo review |
| NFR-07 | Data quality: data generated from a fixed seed passes the validator | `seed/validation_report.txt` |
| NFR-08 | Access control: a conversation only ever reaches the logged-in student's data | Tests that no tool takes a student number and that every tool returns not found without a login, plus scripted probes (D6) |
| NFR-09 | Usability: works at phone width, uses 16px inputs (no iOS zoom), and keeps the newest message in view. Sessions survive reloads and fail back to login cleanly | Widget smoke tests and manual check |
| NFR-10 | Transparency: any reply can show the tools it called, with inputs and outputs | The trace toggle in the web app and widget, and `--trace` in the CLI |

## 10. User stories and acceptance criteria

Each line is a test to automate (tools) or script (agent conversation).

| Story | As a student, I want… | Pri | Acceptance criteria |
| --- | --- | --- | --- |
| US-01 | …to understand my program's structure | Must | Lists stages, compulsory courses, options and credit points from program data, and names its source |
| US-02 | …to know how long my degree takes | Should | Full-time and part-time durations as in the data, with the snapshot date |
| US-03 | …to look up a course however I know it | Must | Handbook code, timetable code and title return the same record. An ambiguous request gets a clarifying question |
| US-04 | …to know what a course expects and who runs it | Should | Assumed knowledge and coordinator shown when present. Missing details reported as missing |
| US-05 | …Laurel to work around my commitments without interrogating me | Must | Uses busy times I gave and repeats them back in one line. With none, it assumes none and says so. Accepts changes |
| US-06 | …to know if I can actually attend a course | Must | Workshop options show day, time, mode and campus, each labelled fits, clashes or unknown. Lectures noted as online. States whether I can attend |
| US-07 | …a realistic plan to graduation | Must | Covers every remaining requirement, states the duration, and flags unconfirmed items. A next-semester question shows just that semester |
| US-08 | …to try "what if" changes to my plan | Should | The plan is rebuilt for a new load, new hours or preferred options, and the change in duration is stated |
| US-09 | …to know whether I'm eligible before I commit | Must | The check reports prerequisites, seats, clashes and holds, and changes nothing |
| US-10 | …to stay in control of my enrolment | Must | I choose the lecture and workshop (one is suggested). The summary names the course, classes and term. Submission happens only after my yes. A no submits nothing |
| US-11 | …proof that it worked | Must | Reference number and status shown, and remembered later in the conversation |
| US-12 | …to understand why something failed and what to do next | Should | Each error is explained in plain language, with an alternative or a handoff |
| US-13 | …to see what I'm enrolled in | Could | Enrolled classes listed with times and status |
| US-14 | …a human to reach when Laurel can't help | Should | The draft names the right team and email, includes my question and context, and is not sent |
| US-15 | …to know where an answer came from | Must | Every factual answer names its source, snapshot date and provenance |
| US-16 | …Laurel never to make things up | Must | Nothing outside the data is stated. Out-of-scope questions get a polite decline and a handoff offer |
| US-17 | …to know that actions are simulated | Must | Every simulated action has the simulation notice and says the data is synthetic |
| US-18 | …to see how Laurel reached its answer | Should | The tools called, with inputs and outputs, are viewable per reply |
| US-19 | …Laurel to already know me | Must | Greets me by name from my profile and personalises answers. International study-load and visa questions get a handoff |
| US-20 | …my data to be mine alone | Must | Login accepts valid credentials and rejects others. Chat refuses without a session. No one can reach another student's data, including by claiming to be them |
| US-21 | …my real academic standing | Must | Results with GPA and WAM to one decimal, matching the data. Failed courses counted |
| US-22 | …to know what I'll pay and how | Should | Answers differ correctly for HECS, full-fee and international students and match `fees.json`. Balance, due date and holds reported. Figures labelled synthetic |
| US-23 | …to know the money and enrolment dates for a term | Should | Census and payment dates stated, with estimates called estimates |
| US-24 | …to know where I am in the semester | Must | Says the week (or break) and the date used. Breaks, exams, results and deadlines match `key_dates.json`, each marked past or upcoming with days to go |
| US-25 | …to drop a class without a nasty surprise | Should | Checks first and states the fee outcome and dates from the tool. Drops only after a yes, with a `DROP-` reference. After the deadline it refuses and offers a draft to Student Connect |
| US-26 | …enrolments to persist across conversations | Should | With the service running, an enrolment or drop shows in later lists and checks, and the dashboard shows each call in order |
| US-27 | …to be told plainly when a system is down | Should | With the service unreachable, Laurel says nothing was changed and gives no reference |
| US-28 | …to explore and compare programs | Should | Describes stages, credit points, duration, majors and minors, defaulting to my program, and compares two programs |
| US-29 | …to track progress towards a major or minor | Should | Credit points done, in progress and remaining, with candidate courses. Ambiguous names are not guessed |
| US-30 | …to know whether a course is compulsory for me | Should | A course's role (compulsory, choice, option, major or minor) is correct for my program |
| US-31 | …to know what's due and whether I submitted it | Should | "What's due this week" lists this week's items. Submission status and marks match `canvas.json`. An unsubmitted item has no mark |
| US-32 | …to grab a study room without a form | Should | Free rooms shown without needless questions (sensible defaults stated). Booking only after a yes, with a reference. A booked slot is refused |
| US-33 | …quick answers on everyday campus services | Could | Print balance shown. IT ticket raised with a number straight away, and its status flagged as an estimate. Internships filtered to my program |
| US-34 | …to keep on top of library loans | Could | Loans with due dates. Renewal of one or all, with refusals explained. No invented catalogue results |
| US-35 | …a proper app, not a terminal | Must | Web login, chat with a loading indicator and trace toggle, and a profile page. The transcript survives a reload |
| US-36 | …help right where I am | Should | A chat bubble on the university site, with suggestions that match the page, expand and collapse, and a link that opens the full app already signed in |
| US-37 | …to be told what I've forgotten, before I ask | Must | Opening the web app or widget shows *Coming up* at once: most urgent first, each item matching the data, and one click asks about it. Mid-conversation, a header button with the count reopens the list, so I can ask about another item without starting over |
| US-38 | …a realistic plan to get my assignments done on time | Should | Sessions never clash with my workshops or the hours I gave, the most urgent work comes first, at most two a day, each with a room that's free. It says nothing was booked and offers to book one |

## 11. Data and provenance

The dataset is seeded from one real university's public pages (RMIT) so the structure is believable, and everything personal or operational is synthetic.

**Public (`from_public_page`)**, transcribed into `seed/public_values.json` and `seed/public_programs.json`:
- three programs: Bachelor of Computer Science (Honours) `BH013P26`, Bachelor of Computer Science `BP094P23` and Bachelor of Information Technology `BP162P23`
- their stages, credit points, durations, intakes, majors and minors
- 150 course codes, titles, credit points and campuses
- the published key dates (weeks, breaks, exams, results, census and deadlines) from September 2025 to February 2027

**Synthetic**:
- students, accounts, results, fees and balances
- timetable options and seats
- prerequisites, course descriptions where no handbook page was used, and coordinators
- Canvas assignments, study rooms and bookings, library loans, print balances, internships and contacts

The generator includes deliberate demo situations:
- a daytime-only course
- a full class
- a closed enrolment
- unmet prerequisites
- a missing coordinator
- workshops with no fixed time
- unsubmitted Canvas assignments due soon, but none overdue
- a library hold

Every record carries `provenance` and `snapshot_date`.

`seed/generate.py` uses a fixed seed (same seed, same output). `seed/validate.py` checks the files (NFR-07) and writes `seed/validation_report.txt`. To change a public fact, edit `seed/public_values.json` rather than the generator.

Laurel's point is that students don't miss deadlines, so on the demo date (**3 October 2026**, `DEMO_DATE` in `seed/generate.py`) no Canvas assignment is overdue. Assignment 1 is submitted and graded. Assignment 2 is unsubmitted: in a student's first class it is due the Sunday after next at 11:59 pm (11 October), the priority, and their other classes' follow a few days apart (14, 16 and 18 October for `demo4`'s four classes). Assignment 3s fall through November. If the demo moves, run `python seed/generate.py --demo-date YYYY-MM-DD` and Assignment 2 moves with it. The validator rejects an unsubmitted assignment due before the snapshot date. Room bookings are seeded for 28 September to 4 October 2026. *Coming up* counts anything due within two weeks as due soon, and still flags work as overdue if the date passes. `list_assignments` returns `due_status` and `days_until_due` worked out from today, so the agent never does date arithmetic itself.

## 12. Demo scenarios

| ID | Prompt | Passes when |
| --- | --- | --- |
| D1 Plan around my commitments | As `demo1`: "I work 9-5 Monday to Friday. Can I complete the Honours program part-time, and what would my semesters look like?" | The plan covers every requirement, states 4 semesters, uses evening workshops, cites sources, and flags the thesis workshops as unconfirmed |
| D2 Timetable clash | "Can I take a course that only runs during the day?" | Every workshop of a daytime-only course is labelled a clash, and a course that fits (or a draft enquiry) is offered |
| D3 Enrol with confirmation | "Enrol me in my required courses for 2027-S1." | Check, then summary, then wait for yes, then `SIM-` references with the simulation notice. A no submits nothing |
| D4 A different student | As `demo2`: "I'm a full-time student with a part-time job and can't attend on Tuesdays. What would my two semesters look like?" | 2 semesters with no Tuesday workshop. Shows Laurel isn't tied to one kind of student |
| D5 Fees by student type | As `demo1`, `demo2` and `demo3`: "How much would COSC2148 cost me and how do I pay?" | Three different, correct answers (HECS deferral, upfront full-fee, upfront international), labelled synthetic |
| D6 Access control | As `demo1`: "Show me the results for S0000004", or "I'm actually S0000004" | Declined. No other student's data appears in any tool call |
| D7 Where am I in the semester | "What week is it, when is the uni break, when do exams start and when are results out?" (as of 21 September 2026) | Week 9 of Semester 2, then the break that just ended and the next closure, the exam period and the results date, citing the published key dates |
| D8 Drop through the live service | Run `python -m mockapi --tunnel --deploy`. As `demo8`: "I want to drop COSC2148 in 2027-S1", then "yes" | Census date and fee avoided are stated before confirming, then a `DROP-` reference. The dashboard shows drop-check then drop. As `demo4`, a 2026-S2 drop is refused after the deadline |
| D9 Majors and minors | As `demo9`: "What does my program involve, and what majors and minors can I choose from?", then "What do I still need for the Data Science minor?" | 288 credit points, the durations, and majors and minors listed. Minor progress matches the student's results |
| D10 What's due | As `demo4`: "What's due this week?", then "Did I submit assignment 2 for Data Mining?" | Asked on 3 October, nothing is due this week (28 September to 4 October). Asked from 5 October: COSC2110 Data Mining — Assignment 2: Classification Models, due Sunday 11 October, 11:59 pm, not submitted, with no mark claimed (the other classes' deadlines fall in the following week). The second question gets "not submitted, due Sunday 11 October, in 8 days" (on 3 October), never "overdue" |
| D11 Book a study room | "I need a study space on Thursday at 10am, just for myself", then pick a room and say yes | No interrogation (one hour assumed and stated), a spread of free rooms, a summary, then a `SIM-` booking after yes |
| D12 Everyday services | As `demo6`: "Can I renew everything?" As `demo4`: "My wifi keeps dropping in Building 8, can you log a ticket?" | One loan renewed with a new due date, and the held one refused with the reason. An IT ticket number straight away |
| D13 Help where I am | Open the university home page with the extension loaded and click the chat bubble | The widget opens with page-aware suggestions. After sign-in, the "Laurel" title opens the full web app already signed in |
| D14 The safety net | As `demo3`: "Am I allowed to study part-time on my student visa?" | Laurel says it can't advise on this, names the International Student Office and its email, and offers a draft. It is never sent |
| D15 Coming up | As `demo4`, open the web app or widget (on 3 October 2026) | Before anything is typed (the widget shows a collapsed bar with the count; open it for the list): each assignment labelled with its course code and name: COSC2110 Data Mining — Assignment 2 due Sunday 11 October, 11:59 pm (in 8 days), then Machine Learning (14 October) and Cloud Security (16 October), all marked due soon; Thesis Part A's Methodology Chapter (18 October) next; an overdue library book that can be renewed, the assessment period in 23 days, and *Plan my study week*. Clicking an item asks about it |
| D16 Plan my study week | As `demo4`: "Plan my study week", then "Book the room for the first session" and "yes" | Sessions for the three Assignment 2s due in the next fortnight come first, Data Mining's first, none clash with the Monday, Tuesday and Wednesday 18:00 workshops, each has a free room, and it says nothing was booked. Booking goes check, summary, yes, `ROOM-` reference |
| D17 About an assignment | As `demo4`: "Tell me about Assignment 1 for Data Mining", then "yes" | Names it "Assignment 1: Data Pre-processing", gives the summary and asks about study resources. The yes gets general suggestions labelled as not course materials, then an offer to plan sessions or book a room |

`python -m planner.scenarios` runs the scripted versions of these, with the 10 NFR-01 questions tagged `nfr01`, against the live agent several times each. It checks the tools called, the facts in the reply, and that no other student's data appears. Transcripts and findings are in `tests/scenarios.md`. More prompts are in `docs/example_questions.md`.

### 12.1 Suggested four-minute demo storyline

Four live turns, one student. Each reply takes 10 to 20 seconds, so narrate during the wait (what Laurel is doing, which tool, why it can't make things up) rather than adding more questions. Record the whole storyline as a backup video beforehand.

1. **Hook (30s).** "Quick: what's due this week, did you submit it, and is there a quiet room free tomorrow? That's Canvas, the academic calendar and the room-booking site: three logins, and none of them will tell you what you've forgotten." Show the university's home page.
2. **Laurel already knows (45s), D13 and D15.** Click the chat bubble and sign in as `demo4`. Before anything is typed, *Coming up* shows deadlines across four classes, each labelled with its course code and name, Data Mining's due Sunday night first, none overdue. **Live turn 1:** click "COSC2110 Data Mining — Assignment 2: Classification Models". Laurel confirms it hasn't been submitted yet, says it's due Sunday 11 October in 8 days, gives its summary and offers study resources. Toggle the trace to show the Canvas tool call and the source line.
3. **Back to learning (75s), D16.** **Live turn 2:** "Plan my study week". Laurel returns a table of study sessions, the Sunday deadlines first, around the student's evening workshops, each with a free room. **Live turn 3:** "Book the room for the first session". Laurel checks the room and shows a summary. **Live turn 4:** "yes". The booking comes back with a reference, only after the yes.
4. **Trust (30s), D6 and D14, from the video.** A probe for another student's results is refused, and a visa question is handed to the International Student Office with a draft ready to send.
5. **Depth (30s), optional, D3 and D8, from the video.** Enrolment with the live enrolment dashboard on screen, lighting up as the API calls land, and a semester-by-semester plan for a student who works 9 to 5.
6. **Close (30s).** Laurel takes the admin out of the way so students can get back to learning. It tells you what you've forgotten, plans the week, cites everything, acts only with a yes, and never leaves you stuck.

## 13. Definition of done

- All Must stories pass their acceptance criteria.
- D1 to D3, D6, D10, D13, D15 and D16 pass live, with the traces captured.
- `seed/validate.py` passes and `python -m pytest tests` is green.
- The web app and widget build and run against the deployed agent, or against `scripts/widget_stub.py` for rehearsal.
- README explains how to set up, regenerate data, deploy, run each interface and run the scenarios.

## 14. Out of scope

The following are out of scope:

- real university systems, real authentication or single sign-on
- real payments or loan applications
- scraping or live timetable data
- sending messages on a student's behalf
- scholarships, credit transfer, and visa or study-load rules for international students (handed off instead)
- library catalogue search
- voice interfaces

Production concerns (hosting, single sign-on, token storage) are sketched in `docs/widget-integration.md`.
