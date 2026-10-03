import styles from "./Spinner.module.css";

// A plain two-tone ring, not the logo: a uniform-stroke ring has full rotational symmetry, so spinning it
// (the previous approach, reusing LaurelLogo) is visually static — every rotation angle looks identical.
// This one has a distinct light track and a brighter moving arc, so the rotation actually reads.
export default function Spinner({ size = 18 }) {
  return <span className={styles.spinner} style={{ width: size, height: size }} aria-hidden="true" />;
}
