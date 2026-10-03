import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import LaurelLogo from "./LaurelLogo";
import WeekMenu from "./WeekMenu";
import styles from "./NavBar.module.css";

// week and onAsk are given only on the chat page once a conversation has started: Your week then lives here.
export default function NavBar({ week, onAsk, askDisabled }) {
  const { username, studentNumber, logout } = useAuth();
  return (
    <nav className={styles.nav}>
      <Link to="/" className={styles.brand}>
        <LaurelLogo size={22} />
        <span className={styles.brandName}>Laurel</span>
        <span className={styles.badge}>Prototype</span>
      </Link>
      <Link to="/" className={styles.link}>
        Chat
      </Link>
      <Link to="/profile" className={styles.link}>
        Profile
      </Link>
      <span className={styles.spacer} />
      {week && onAsk && <WeekMenu week={week} onAsk={onAsk} disabled={askDisabled} />}
      <span className={styles.user}>
        {username} ({studentNumber})
      </span>
      <button type="button" className={styles.logoutBtn} onClick={logout}>
        Log out
      </button>
    </nav>
  );
}
