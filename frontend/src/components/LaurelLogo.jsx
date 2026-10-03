import laurel from "../assets/laurel.png";
import laurelNoFace from "../assets/laurel-no-face.png";

// The Laurel mark: the white laurel leaves, centred on a red disc. The plain leaves for small sizes (the nav
// bar); with faces for the login page's large mark. Source artwork is in assets/brand/.
export default function LaurelLogo({ size = 28, faces = false, className }) {
  return (
    <span
      role="img"
      aria-label="Laurel"
      className={className}
      style={{
        display: "block",
        flex: "none",
        width: size,
        height: size,
        borderRadius: "50%",
        background: "var(--accent, #e4002b)",
      }}
    >
      <img src={faces ? laurel : laurelNoFace} alt="" width={size} height={size} style={{ display: "block" }} />
    </span>
  );
}
