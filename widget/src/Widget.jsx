import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { makeApi } from "./api";
import { watchCorner } from "./avoidCollisions";
import { chipsForPath } from "./pageContext";
import { prefs } from "./transport";
import { useChat } from "./useChat";
import ChatInput from "./components/ChatInput";
import LoadingIndicator from "./components/LoadingIndicator";
import LoginForm from "./components/LoginForm";
import Message from "./components/Message";
import WeekBox from "./components/WeekBox";
import WeekItems, { weekCount } from "./components/WeekItems";
import { CalendarIcon, ChatIcon, ChevronDownIcon, CloseIcon, CollapseIcon, ExpandIcon, PhoneIcon, SignOutIcon, TraceIcon } from "./icons";

// RMIT's main switchboard, as published on rmit.edu.au/contact. Check it is still current before demoing.
const ENQUIRIES_PHONE = { display: "+61 3 9925 2000", tel: "+61399252000" };
const CONTACT_URL = "https://www.rmit.edu.au/contact";

const MODEL_LABEL = "Orchestrate · Frontier";

export default function Widget({ transport, showDemoHint = true }) {
  const api = useMemo(() => makeApi(transport), [transport]);
  const [open, setOpen] = useState(() => prefs.get("open") === "1");
  const [auth, setAuth] = useState({ status: "checking" }); // checking | out | in
  const [firstName, setFirstName] = useState(null);
  const [week, setWeek] = useState(null);
  const [traceVisible, setTraceVisible] = useState(() => prefs.get("showTrace") === "true");
  const [phoneOpen, setPhoneOpen] = useState(false);
  const [weekOpen, setWeekOpen] = useState(false);
  const [expanded, setExpanded] = useState(() => prefs.get("expanded") === "1");
  const [bottom, setBottom] = useState(24);
  const rootRef = useRef(null);
  const loaded = useRef(false);
  const listRef = useRef(null);
  const inputWrapRef = useRef(null);

  // Sit above any other fixed element (another chat button, a cookie banner) in the same corner.
  useEffect(() => {
    const host = rootRef.current && rootRef.current.getRootNode().host;
    return host ? watchCorner(host, setBottom) : undefined;
  }, []);

  const onUnauthorised = useCallback(() => setAuth({ status: "out" }), []);
  const { messages, sending, send, retry, loadHistory, reset } = useChat(api, { onUnauthorised });

  // Is there already a session? (The token, if any, is held by the transport, not by this component.)
  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((d) => !cancelled && setAuth(d.logged_in ? { status: "in", username: d.username } : { status: "out" }))
      .catch(() => !cancelled && setAuth({ status: "out" }));
    return () => {
      cancelled = true;
    };
  }, [api]);

  // Fetch the name and recover the conversation the first time the panel is opened while signed in, not on
  // every page load: this is a widget on someone else's site, so it stays quiet until it is used. History
  // comes from the server, which is how a conversation follows the student from one page to the next.
  useEffect(() => {
    if (!open || auth.status !== "in" || loaded.current) return;
    loaded.current = true;
    // A 401 here means the backend no longer knows this session (it restarted): show the sign-in form rather
    // than a signed-in panel that silently has no name and no week.
    const signedOutIf401 = (err) => {
      if (err && err.status === 401) {
        loaded.current = false;
        setAuth({ status: "out" });
      }
    };
    api
      .profile()
      .then((d) => d.found && setFirstName(String(d.student.name).split(" ")[0]))
      .catch(signedOutIf401);
    api
      .week()
      .then((d) => d.found && setWeek(d))
      .catch(signedOutIf401);
    loadHistory();
  }, [open, auth.status, api, loadHistory]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, sending, open, auth.status]);

  useEffect(() => {
    if (open && auth.status === "in") inputWrapRef.current?.querySelector("input")?.focus();
  }, [open, auth.status]);

  function setOpenPref(next) {
    setOpen(next);
    prefs.set("open", next ? "1" : "0");
  }

  async function handleLogin(username, password) {
    const user = await api.login(username, password);
    loaded.current = false;
    reset();
    setAuth({ status: "in", username: user.username });
  }

  async function handleLogout() {
    try {
      await api.logout();
    } catch {
      // the token is dropped either way
    }
    loaded.current = false;
    reset();
    setFirstName(null);
    setWeek(null);
    setWeekOpen(false);
    setAuth({ status: "out" });
  }

  // The header's Your week, for once a conversation has started: refreshed on opening (no model call), and
  // mutually exclusive with the phone popover so only one sheet sits under the header at a time.
  function toggleWeek() {
    const next = !weekOpen;
    setWeekOpen(next);
    if (next) {
      setPhoneOpen(false);
      api
        .week()
        .then((d) => d.found && setWeek(d))
        .catch(() => {});
    }
  }

  function askAboutWeekItem(prompt) {
    setWeekOpen(false);
    send(prompt);
  }

  function toggleExpanded() {
    const next = !expanded;
    setExpanded(next);
    prefs.set("expanded", next ? "1" : "0");
  }

  function toggleTrace() {
    const next = !traceVisible;
    setTraceVisible(next);
    prefs.set("showTrace", String(next));
  }

  const chips = useMemo(() => chipsForPath(window.location.pathname), []);
  const hasConversation = messages.length > 0;
  const weekItemCount = weekCount(week);
  // On the start screen Your week is in the body; once chatting, it moves to a header button.
  const showWeekButton = auth.status === "in" && weekItemCount > 0 && (hasConversation || sending);
  const sizeLabel = expanded ? "Make the chat window smaller" : "Make the chat window larger";
  const traceLabel = traceVisible ? "Hide the tool-call trace" : "Show the tool-call trace";

  return (
    <div className="lw-widget" data-open={open ? "true" : "false"} data-expanded={expanded ? "true" : "false"} ref={rootRef} style={{ "--lw-bottom": `${bottom}px` }}>
      <section
        className="lw-panel"
        role="dialog"
        aria-label="Laurel chat"
        aria-hidden={!open}
        onKeyDown={(e) => {
          if (e.key !== "Escape") return;
          if (weekOpen) setWeekOpen(false);
          else if (phoneOpen) setPhoneOpen(false);
          else setOpenPref(false);
        }}
      >
        <header className={`lw-header${showWeekButton ? " lw-header-crowded" : ""}`}>
          <span className="lw-mark">
            <ChatIcon size={18} />
          </span>
          <div className="lw-title">
            <div className="lw-title-row">
              <button
                type="button"
                className="lw-brand-link"
                title="Open the full Laurel web app"
                onClick={() => api.openWebapp().catch((e) => console.error("Could not open the full webapp:", e))}
              >
                Laurel
              </button>
              <span className="lw-badge">Prototype</span>
            </div>
            <span className="lw-model">{MODEL_LABEL}</span>
          </div>
          {showWeekButton && (
            <button
              type="button"
              className={`lw-header-btn lw-week-btn${weekOpen ? " lw-on" : ""}`}
              title="Your week"
              aria-label={`Your week, ${weekItemCount} items`}
              aria-expanded={weekOpen}
              onClick={toggleWeek}
            >
              <CalendarIcon size={18} />
              <span className="lw-header-badge" aria-hidden="true">
                {weekItemCount}
              </span>
            </button>
          )}
          <button
            type="button"
            className={`lw-header-btn${phoneOpen ? " lw-on" : ""}`}
            title="Call RMIT"
            aria-label="Call RMIT"
            aria-expanded={phoneOpen}
            onClick={() => {
              setPhoneOpen(!phoneOpen);
              setWeekOpen(false);
            }}
          >
            <PhoneIcon size={18} />
          </button>
          <button
            type="button"
            className="lw-header-btn lw-size-btn"
            title={sizeLabel}
            aria-label={sizeLabel}
            aria-pressed={expanded}
            onClick={toggleExpanded}
          >
            {expanded ? <CollapseIcon size={18} /> : <ExpandIcon size={18} />}
          </button>
          {auth.status === "in" && (
            <button type="button" className="lw-header-btn" title="Sign out" aria-label="Sign out" onClick={handleLogout}>
              <SignOutIcon size={18} />
            </button>
          )}
          <button type="button" className="lw-header-btn" title="Minimise" aria-label="Minimise chat" onClick={() => setOpenPref(false)}>
            <ChevronDownIcon size={20} />
          </button>
        </header>

        {weekOpen && showWeekButton && (
          <div className="lw-weekdrop" role="region" aria-label="Your week">
            <p className="lw-weekdrop-head">
              <strong>Your week</strong>
              {week.week_label && <span className="lw-dim"> · {week.week_label}</span>}
            </p>
            <div className="lw-weekdrop-list">
              <WeekItems week={week} onAsk={askAboutWeekItem} />
            </div>
          </div>
        )}

        {phoneOpen && (
          <div className="lw-phone" role="region" aria-label="RMIT general enquiries">
            <div>
              <span className="lw-phone-label">RMIT general enquiries</span>
              <a className="lw-phone-number" href={`tel:${ENQUIRIES_PHONE.tel}`}>
                {ENQUIRIES_PHONE.display}
              </a>
              <a className="lw-phone-more" href={CONTACT_URL} target="_blank" rel="noopener noreferrer">
                More ways to contact RMIT
              </a>
            </div>
            <button type="button" className="lw-header-btn lw-phone-close" aria-label="Close" onClick={() => setPhoneOpen(false)}>
              <CloseIcon size={16} />
            </button>
          </div>
        )}

        <div className="lw-body" ref={listRef} role="log" aria-live="polite">
          {auth.status === "out" && <LoginForm onLogin={handleLogin} showDemoHint={showDemoHint} />}
          {auth.status === "in" && !hasConversation && !sending && (
            <div className="lw-empty">
              <h2>{firstName ? `Hi ${firstName}, how can I help?` : "Hi, how can I help?"}</h2>
              {week && week.items.length > 0 ? (
                <WeekBox week={week} onAsk={send} />
              ) : (
                <p className="lw-dim">Ask about your enrolment, results, timetable, library loans, study rooms and more.</p>
              )}
              <div className="lw-chips">
                {chips.map((chip) => (
                  <button key={chip} type="button" className="lw-chip" onClick={() => send(chip)}>
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          )}
          {auth.status === "in" && (hasConversation || sending) && (
            <div className="lw-list">
              {messages.map((m, i) => (
                <Message
                  key={i}
                  message={m}
                  traceVisible={traceVisible}
                  onRetry={m.role === "assistant" ? () => retry(i) : undefined}
                  retryDisabled={sending}
                />
              ))}
              {sending && <LoadingIndicator />}
            </div>
          )}
        </div>

        <footer className="lw-footer">
          {auth.status === "in" && (
            <div ref={inputWrapRef}>
              <ChatInput onSend={send} disabled={sending} placeholder={hasConversation ? "Reply" : "How can I help you today?"} />
            </div>
          )}
          <div className="lw-fine">
            {auth.status === "in" && (
              <button
                type="button"
                className={`lw-icon-btn${traceVisible ? " lw-active" : ""}`}
                title={traceLabel}
                aria-label={traceLabel}
                aria-pressed={traceVisible}
                onClick={toggleTrace}
              >
                <TraceIcon size={14} />
              </button>
            )}
            <span>Laurel is AI and can make mistakes. Prototype, synthetic data.</span>
          </div>
        </footer>
      </section>

      <button
        type="button"
        className="lw-launcher"
        aria-label={open ? "Close Laurel chat" : "Open Laurel chat"}
        aria-expanded={open}
        onClick={() => setOpenPref(!open)}
      >
        {open ? <ChevronDownIcon size={28} /> : <ChatIcon size={30} />}
      </button>
    </div>
  );
}
