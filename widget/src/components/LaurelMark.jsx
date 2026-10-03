import laurel from "../assets/laurel.png";
import laurelNoFace from "../assets/laurel-no-face.png";

// The Laurel leaves (assets/brand/), white on transparent, sized to fill the red disc they sit on: the plain
// leaves for small marks, the version with faces for the sign-in screen's large one. The library build
// inlines both images into laurel-widget.js, so they work inside the extension too.
export default function LaurelMark({ size, faces = false }) {
  return <img src={faces ? laurel : laurelNoFace} alt="" width={size} height={size} style={{ display: "block" }} />;
}
