# Laurel

**One front door to university life.** A student's everyday questions are scattered across a dozen systems: Canvas, the handbook, the timetable, enrolment, fees, the academic calendar, the library, room booking and the IT desk. Laurel is a conversational assistant that already knows who you are. The moment you open it, *Coming up* shows what's overdue, what's due soon and what's coming up, and one click asks about it or plans your study week around your classes. It answers from your own data with a source on every reply, and it takes action for you (enrol, drop, book a room, renew a loan, log a ticket) only after you say yes. It takes the admin out of the way so you can get back to learning. When it can't help, it names the right team and drafts the email for you to send.

Built for the CSIT hackathon (*Innovating Education*) on IBM watsonx Orchestrate, using synthetic data. Laurel runs in three places: a chat widget on the university's own pages, a web app and a CLI. See [docs/requirements.md](docs/requirements.md) for the problem, scope, how it maps to the judging criteria, and the demo storyline.

## Approach and architecture

This is a **tool-calling agent**, not a document-search system. There is no vector store, no embeddings and no unstructured corpus to search: a foundation model reads the student's message against a fixed instruction set, decides which of 30 Python functions to call and with what arguments, gets a structured JSON result back, and writes the reply from that — always citing where the fact came from. Every "retrieval" is an exact, deterministic lookup or computation over small JSON files, not a similarity search.

```
planner CLI (login, chat)
   │  sends: user message + run context {student_number}
   ▼
IBM watsonx Orchestrate ──runs──► study_planner_agent (instructions + tool list + model choice)
   │                                     │
   │                                picks a tool, calls it with arguments inferred from the message
   ▼                                     ▼
Python tools (tools/*_tools.py) ──read──► JSON data files (data/*.json)
   │                                     or, for enrol/drop, an HTTP call to the mock service (mockapi/)
   ▼
tool returns a JSON dict (facts + a "source" block)
   │
   ▼
model turns that JSON into the reply sent back to the CLI
```

### The layers

- **Data** — `data/*.json`: 3 programs, 150 courses, a timetable, students, fees, key dates. Generated deterministically by `seed/generate.py` from public facts in `seed/public_values.json` / `seed/public_programs.json`, checked by `seed/validate.py`. Every record carries `provenance` (`from_public_page` or `synthetic`).
- **Tools** — `tools/*.py`: plain Python functions decorated with `@tool`. Each one loads specific files (via a cached `tools/common.py:load`), does an exact lookup, filter or computation, and returns a JSON-serialisable dict with a `source` block. A tool's docstring is what the model actually sees to decide when and how to call it.
- **Identity and isolation** — a `context: AgentRun` parameter lets a tool read `context.request_context["student_number"]`, set by the CLI from the authenticated login session. The model never sees or supplies a student number, so it cannot be asked or tricked into fetching someone else's data.
- **Programs are data, not code** — `data/programs.json` models a program as a list of stages, each an ordered list of items (`course`, `options` or `choice`). `tools/programs.py` resolves "the student's program" from their login and provides the shared helpers every program-aware tool uses, so adding a program is a data change, not a rewrite.
- **The confirmation pattern** — every action that changes something (enrol, drop) is split into a `check_*` tool with no side effect and a paired action tool that refuses unless it is given a matching `check_id` and an explicit `student_confirmed: true`. The agent's instructions require it to check, show a summary, wait for a clear yes on the *next* message, and only then call the action tool — never in the same reply as the check.
- **Optional live service** — `mockapi/` is a small FastAPI service that stands in for a real enrolment system, with an in-memory store and a live dashboard of every request. When it is configured (an address and key written into the deployed package at deploy time), the enrolment and drop tools call it over HTTPS instead of computing locally; if it is configured and unreachable, they say so and change nothing rather than falling back silently. Reached through a free Cloudflare tunnel for the demo (`python -m mockapi --tunnel --deploy`).
- **The human safety net** — `draft_enquiry` is what the agent calls instead of guessing when a question is out of scope or the data doesn't have an answer. It first names the right team and asks whether the student wants a draft; only on a yes does it write one (`include_draft`). It only ever drafts; nothing is sent, and the student sends it themselves.
- **Client** — `planner/`: a CLI for login/session (`auth.py`), a chat client that sends the run context on every message and can print the tool-call trace (`client.py`), and an automated scenario runner that asks the live agent scripted questions and checks the tools called and the facts in the reply (`scenarios.py`).

### What this is not

Not RAG in the technical sense — there's nothing to embed or chunk, and every lookup is exact rather than approximate. The goal it shares with RAG is grounding answers in real data instead of the model's own memory; the mechanism is function calling over structured data, not semantic search over documents.

## Set up

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
orchestrate env add -n trial -u <instance url>     # once
orchestrate env activate trial                     # prompts for the API key; the token expires after a couple of hours, so run it again when imports say the token is expired
```

Don't have an Orchestrate instance yet? Trial access (a 30-day trial was available as of writing) is at
<https://www.ibm.com/products/watsonx-orchestrate>; `<instance url>` and the API key above come from whatever
instance you provision there. Everything else in this repo — the tests, `seed/`, the scripted scenarios, and
`scripts/widget_stub.py` for the widget — runs entirely from the synthetic data with no Orchestrate dependency
at all, so you can explore the whole project before an instance is set up.

## Regenerate data

```
python3 seed/generate.py              # writes the data files in data/ (fixed seed) from seed/public_values.json
python3 seed/validate.py --report     # checks the data, writes seed/validation_report.txt
python3 -m pytest tests               # data, tool and login tests
```

## Import tools and the agent

One command packages the data and tools (never `accounts.json`), imports every tool and the agent, and retries transient platform errors. If the login token has expired it stops and tells you to run `orchestrate env activate`.

```
python scripts/deploy.py                   # everything
python scripts/deploy.py --only timetable  # one tool file
python scripts/deploy.py --dry-run         # print the commands only
```

The steps by hand:

```
python3 scripts/build_package.py
orchestrate tools import -k python -f build/package/tools/student_tools.py -p build/package -r build/package/requirements.txt
orchestrate agents import -f agents/study_planner.yaml
```

## Log in and chat

The login is a placeholder for a web login. The CLI sends only your student number to the agent, in the run context, so a conversation is tied to one student and the agent never asks who you are.

```
python -m planner login            # prompts for username and password
python -m planner whoami
python -m planner chat --trace     # interactive; --trace shows the tool calls behind each reply
python -m planner ask "..." --plain   # plain text with no coloured panels, for scripts and logs
python -m planner ask "How is my GPA worked out?" --trace
python -m planner logout
```

For a scripted run use `python -m planner login -u demo1 -p demo1`. To switch student, log out, log in as another account and start a new conversation.

## Run the web app

**Laurel** — a browser front end for the same agent: log in to a home screen that opens on *Coming up* (work due soon and coming up, holds, library books and key dates, straight from the tools with no wait, and one click away from the nav bar once you're chatting), chat (with a trace toggle and a livelier "thinking" indicator) and a profile page, no CLI needed. The backend (`webapp/`) reuses the same `planner.auth`/`planner.client` code the CLI uses, so both can be logged in at once, even as different students, and neither affects the other. The frontend (`frontend/`) is a React app (Vite, plain JavaScript), styled to match the RMIT theme the chat widget below uses: a navy header bar, RMIT red and white throughout, sans-serif text, and the Laurel mark (white laurel leaves on a red disc; source artwork in `assets/brand/`) as the logo.

Build the frontend once (and again after changing anything under `frontend/src`):

```
cd frontend
npm install
npm run build
cd ..
```

Then run the app:

```
python -m webapp                  # http://127.0.0.1:8100, opens a browser tab
python -m webapp --port 9000 --no-open
```

If `frontend/dist/` is missing, `python -m webapp` fails with the exact `npm` commands above rather than an unhelpful error. Log in with a demo account (e.g. `demo1` / `demo1`). Sessions are in-memory only — a restart logs everyone out, the same trade-off already made by the mock enrolment service below. Logging out before killing the webapp is advised: an already-open tab left logged in across a restart is harmless (it notices and returns to the login page on its own, the next time it regains focus or you try to use it) but a clean logout first avoids that moment altogether. The chat page recovers your transcript if you reload mid-conversation; the trace toggle is a pill button under the chat box (not the header) and needs no reload to show or hide.

For frontend development with live reload, `cd frontend && npm run dev` runs Vite's own dev server (a different port) alongside `python -m webapp` for the API — but for just trying the app out, the build-then-run steps above are all you need.

## Chat widget for RMIT pages (prototype)

A floating red chat button that lives on RMIT web pages: fixed bottom-right, it opens a small RMIT-styled chat window on the same page, with an in-window sign-in (asked for again each browser session) and the same behaviour as the webapp: a "Calculating…" style spinner, copy / thumbs / retry, a trace toggle, and a conversation that follows you between pages. The header also has a phone button (RMIT's general-enquiries number), an expand button (a larger window on the same page), and the "Laurel" name itself, which opens the full webapp in a new tab, signed in already if the widget already was. It is one widget with two hosts: a **Chrome extension** that puts it on the real `www.rmit.edu.au`, and a **saved copy of the page** served by the backend as the offline fallback. See `docs/widget-integration.md` for how all of this fits together.

```
cd widget && npm install && npm run build:extension      # builds the widget and copies it into extension/
python -m webapp --no-open                              # backend on http://127.0.0.1:8100
# Chrome: chrome://extensions -> Developer mode -> Load unpacked -> the extension/ folder, then open https://www.rmit.edu.au/
```

No Orchestrate trial handy? `python scripts/widget_stub.py` runs the same backend with a canned agent (replies start "(stub)") for building and rehearsing. See [docs/widget-integration.md](docs/widget-integration.md) for the architecture, the demo-day checklist, the tests (`npm run smoke`), and how a real deployment would differ (single sign-on, hosting, token storage).

## Demo accounts

Each password is the same as the username.

| Login | Student | Situation |
| --- | --- | --- |
| demo1 | S0000001 | New, domestic, HECS, part-time around a 9-to-5 week |
| demo2 | S0000002 | New, domestic full-fee, full-time |
| demo3 | S0000003 | New, international, full-time |
| demo4 | S0000004 | Continuing, full-time, four classes this term with staggered deadlines (the hero demo for Coming up) |
| demo5 | S0000005 | Continuing, one failed course |
| demo6 | S0000006 | Final semester, six results |
| demo7 | S0000007 | Overdue balance and an enrolment hold |
| demo8 | S0000008 | Already enrolled for next term |
| demo9 | S0000009 | Bachelor of Computer Science, new, full-time |
| demo10 | S0000010 | Bachelor of Computer Science, part-time, partway through with a minor's courses among their results |
| demo11 | S0000011 | Bachelor of Computer Science, full-time, partway through |
| demo12 | S0000012 | Bachelor of Information Technology, full-time, partway through |
| demo13 | S0000013 | Bachelor of Information Technology, international, full-time |
| demo14 | S0000014 | Bachelor of Computer Science, full-time, close to finishing |

## Questions you can ask

Example prompts for every domain, which demo account to use, and what to expect back — moved to its own file since it's reference material rather than setup: [docs/example_questions.md](docs/example_questions.md).

## Run the mock enrolment service and dashboard

By default the enrolment tools use their own logic and remember nothing between conversations. The mock enrolment service (`mockapi/`) is a small web API that stands in for the university's enrolment system. The agent's enrolment and drop tools call it over HTTPS, so you can watch each call arrive on a live page, and an enrolment or drop it accepts is remembered while it runs: the enrolment shows in the student's list, a class fills up, a dropped course can be enrolled again. State is lost when it stops.

Install the tunnel tool once (free, no account): `brew install cloudflared`. Then use three windows.

```
# window 1: start the service, open a free public tunnel, redeploy the enrolment tools to call it
python -m mockapi --tunnel --deploy

# window 2 (or your browser): the dashboard address and key are printed by window 1
#   https://<random-name>.trycloudflare.com/?key=<key>

# window 3: chat as a student
python -m planner login -u demo8 -p demo8
python -m planner chat --trace
```

Window 1 prints every request as it arrives, and the dashboard shows the same with colours (green 2xx, amber 4xx, red 5xx), filters for check, enrol, list, drop check and drop, and the request and response JSON when you click a line. Beside it are the enrolments the service holds and the seats it has taken or freed. **Reset** clears its memory and the log.

Things to try, in order: as `demo8` ask to drop COSC2148 in 2027-S1 and say yes (a drop check, then a drop), then ask what you are enrolled in (the course has gone); as `demo1` enrol in COSC2148 for 2027-S1, say yes, then ask again (already enrolled) and check the list. Then press Ctrl-C in window 1 and ask to enrol: the agent says the enrolment service is unavailable, that nothing was changed, and gives no reference number.

Options: `--port 8000`, `--key <key>` (default a new random key each start), `--public-url https://...` for a tunnel you started yourself (ngrok, for example), `--today 2026-09-10` to set the date the drop rules use, `--no-open`. Without `--deploy` it only serves. To deploy by hand: `python scripts/deploy.py --only enrolment --skip-agent --api-url <address> --api-key <key>`. To go back to the tools' own logic, run `python scripts/deploy.py --only enrolment --skip-agent`.

Notes: the tunnel address changes on every start, so `--deploy` runs each time and takes about 30 seconds. A brand-new tunnel name can take a minute to resolve on your own machine; the start-up carries on if it cannot confirm it. If the redeploy fails (usually an expired login) the service keeps running and prints the command to retry. Anyone with the address and key can use the API and read the dashboard, so keep it for the demo. Everything is synthetic.

## Run the scripted scenarios

`python -m planner.scenarios` asks the agent the questions in `tests/scenarios.yaml` as the demo students and checks the answers against the data: which tools were called, that the facts are in the reply, that another student's data never appears, and that no reply cites a tool it did not call. Answers vary between runs, so repeat them and read the pass rate. It uses the same client as the CLI and does not touch your login session.

```
python -m planner.scenarios --list
python -m planner.scenarios --repeat 2 --workers 5             # everything, about 3 minutes
python -m planner.scenarios --tag nfr01 --repeat 3             # the 10 scripted questions
python -m planner.scenarios --only keydates --repeat 3
python -m planner.scenarios --skip-tag service --repeat 2       # the tools use their own logic (no service)
python -m planner.scenarios --reset-service --repeat 2          # the tools call the service (see above)
```

Scenarios tagged `service` only make sense with the service running, because they rely on it remembering. Scenarios tagged `stateful` can change what the service remembers, so with `--reset-service` they run one at a time after the others and the service is reset before and after each run. `--reset-service` reads the service address from the last deploy.

It prints each run as it finishes, then a table with the pass rate and median and slowest time per scenario, and writes a JSON report with every reply to `scenario_reports/`. A reply that is a platform error is asked again once and marked as retried. The exit code is 1 if any run fails.

## Try the key dates and see the response time

Each reply ends with `Answered in N.Ns`. `--trace` shows which tools were called. The prompts below name a date, so the answers do not change from day to day (the calendar covers 1 September 2025 to 26 February 2027).

```
python -m planner login -u demo1 -p demo1
python -m planner ask "What week was it on 21 September 2026?" --trace
python -m planner chat --trace
```

| Ask | Expect |
| --- | --- |
| What week was it on 21 September 2026? | Week 9 of Semester 2 (21 to 27 September) |
| What week was it on 4 April 2026? | Not a teaching week: the Semester 1 mid-semester break, 3 to 12 April |
| From 21 September 2026, when do the Semester 2 exams start and how many days is that? | Assessment period 26 October to 13 November, 35 days |
| When are Semester 2 results released? | 30 November 2026 |
| What is the census date for Semester 2, and had it passed by 21 September 2026? | 31 August 2026, yes |
| What is the last day to add classes for Semester 2 for a computing student? | 2 August 2026 (the date for all other schools) |
| When is Melbourne Cup Day in 2026? | Tuesday 3 November 2026 |
| What week is it on 1 June 2027? | Outside the published calendar |
| As of 21 September 2026: what week is it, when is the uni break, when do exams start and when are results released? | Week 9; the break that just ended, then the closure 25 December to 1 January (95 days); exams in 35 days; results in 70 days |

Leave the date out ("What week is it?") to use today's date in Melbourne. Expect about 10 to 20 seconds a question, and longer when several tools are called.
