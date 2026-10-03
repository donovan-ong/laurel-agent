import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import LaurelLogo from "./LaurelLogo";
import styles from "./NavBar.module.css";

export default function NavBar() {
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
      <span className={styles.user}>
        {username} ({studentNumber})
      </span>
      <button type="button" className={styles.logoutBtn} onClick={logout}>
        Log out
      </button>
    </nav>
  );
}
