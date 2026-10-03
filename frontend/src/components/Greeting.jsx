import styles from "./Greeting.module.css";

function timeOfDayGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

// The serif greeting, front and center — the empty-state chat page's centrepiece.
export default function Greeting({ name }) {
  return (
    <h1 className={styles.greeting}>
      {timeOfDayGreeting()}
      {name ? `, ${name}` : ""}
    </h1>
  );
}
