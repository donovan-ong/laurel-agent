import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../hooks/useAuth";
import NavBar from "../components/NavBar";
import Greeting from "../components/Greeting";
import WeekPanel from "../components/WeekPanel";
import MessageList from "../components/MessageList";
import ChatInput from "../components/ChatInput";
import LoadingIndicator from "../components/LoadingIndicator";
import OptionsRow from "../components/OptionsRow";
import styles from "./ChatPage.module.css";

const TRACE_KEY = "showTrace"; // same localStorage key the old plain-JS version used

// A 401 means the backend no longer knows this session at all (it restarted, or the session simply expired -
// sessions are in-memory only and never survive a restart). There is nothing to retry: the right response is
// exactly what the header's own Log out button does, so a dead session self-heals to the login page instead
// of leaving the chat page up and failing every message from then on.
function isExpiredSession(err) {
  return err instanceof ApiError && err.status === 401;
}

// The empty-state (greeting) vs conversation-state (message list) split, matching claude.ai's own layout.
export default function ChatPage() {
  const { username, logout } = useAuth();
  const [studentName, setStudentName] = useState(username);
  const [messages, setMessages] = useState([]);
  const [week, setWeek] = useState(null);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [sending, setSending] = useState(false);
  const [traceVisible, setTraceVisible] = useState(() => localStorage.getItem(TRACE_KEY) === "true");
  const firstScroll = useRef(true);

  // /api/me doesn't carry the display name; /api/profile does, and is cheap (no agent call).
  useEffect(() => {
    let cancelled = false;
    api
      .profile()
      .then((data) => {
        if (!cancelled && data.found) setStudentName(data.student.name);
      })
      .catch((err) => {
        if (!cancelled && isExpiredSession(err)) logout();
        // otherwise fall back to the username already shown by NavBar
      });
    return () => {
      cancelled = true;
    };
  }, [logout]);

  // "Your week" for the empty state: called directly, no agent, so it is there as soon as the page is.
  useEffect(() => {
    let cancelled = false;
    api
      .week()
      .then((data) => {
        if (!cancelled) setWeek(data);
      })
      .catch((err) => {
        if (!cancelled && isExpiredSession(err)) logout();
        // otherwise the panel simply isn't shown
      });
    return () => {
      cancelled = true;
    };
  }, [logout]);

  // Recover the transcript on a reload mid-conversation. Runs before first paint decides whether to show
  // the greeting or the message list, so there's no flash of one immediately replaced by the other.
  useEffect(() => {
    let cancelled = false;
    api
      .chatHistory()
      .then((data) => {
        if (cancelled) return;
        if (data.messages && data.messages.length) setMessages(data.messages);
      })
      .catch((err) => {
        if (!cancelled && isExpiredSession(err)) logout();
        // otherwise: best-effort, an empty transcript is a fine starting point
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [logout]);

  // Shared by a fresh send and a retry — both end the same way: POST the message, append whatever comes
  // back (a reply or an error), clear `sending`. Only what happens *before* this differs.
  async function sendToAgent(text) {
    setSending(true);
    try {
      const data = await api.chat(text);
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply, trace: data.trace }]);
    } catch (err) {
      if (isExpiredSession(err)) {
        logout();
        return;
      }
      const message = err instanceof ApiError ? err.message : "Something went wrong.";
      setMessages((prev) => [...prev, { role: "error", text: message }]);
    } finally {
      setSending(false);
    }
  }

  async function handleSend(text) {
    setMessages((prev) => [...prev, { role: "user", text }]);
    await sendToAgent(text);
  }

  // Drops the assistant reply at `index` (and anything after it, though normally nothing is) and re-asks
  // the user message right before it. This resends the question to the agent's own conversation thread —
  // there's no API to erase a past turn there — so the agent sees it asked twice, even though the UI only
  // shows the new answer. See the plan doc for why that's the accepted trade-off here.
  async function handleRetry(index) {
    if (sending) return;
    const userMessage = messages[index - 1];
    if (!userMessage || userMessage.role !== "user") return;
    setMessages(messages.slice(0, index));
    await sendToAgent(userMessage.text);
  }

  // The page scrolls as a whole (see ChatPage.module.css — no inner scroll region), so "auto scroll to the
  // new text" means the window itself: a new user message, a reply, and the loading indicator appearing or
  // disappearing all change the page's height, so re-run this whenever any of them do. The very first run,
  // right as history finishes loading, jumps straight there instead of animating a long restored transcript
  // into view.
  useEffect(() => {
    if (loadingHistory) return;
    const behavior = firstScroll.current ? "auto" : "smooth";
    firstScroll.current = false;
    requestAnimationFrame(() => {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior });
    });
  }, [messages, sending, loadingHistory]);

  function toggleTrace() {
    setTraceVisible((prev) => {
      const next = !prev;
      localStorage.setItem(TRACE_KEY, String(next));
      return next;
    });
  }

  const hasConversation = messages.length > 0;
  const inputArea = (
    <div className={styles.inputArea}>
      <ChatInput
        onSend={handleSend}
        disabled={sending}
        placeholder={hasConversation ? "Reply" : "How can I help you today?"}
      />
      <OptionsRow traceVisible={traceVisible} onToggleTrace={toggleTrace} />
    </div>
  );

  return (
    <div className={styles.page}>
      <NavBar />
      {loadingHistory ? null : hasConversation ? (
        <div className={styles.content}>
          <MessageList
            messages={messages}
            traceVisible={traceVisible}
            onRetry={handleRetry}
            retryDisabled={sending}
          />
          {sending && <LoadingIndicator />}
          {inputArea}
        </div>
      ) : (
        <div className={styles.emptyContent}>
          <Greeting name={studentName} />
          <WeekPanel week={week} onAsk={handleSend} disabled={sending} />
          {inputArea}
          {sending && <LoadingIndicator />}
        </div>
      )}
    </div>
  );
}
