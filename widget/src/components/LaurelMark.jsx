import mark from "../assets/laurel-no-face.png";

// The Laurel leaves (assets/brand/laurel-no-face.png), white on transparent, sized to fill the red disc it
// sits on. The library build inlines the image into laurel-widget.js, so it works inside the extension too.
export default function LaurelMark({ size }) {
  return <img src={mark} alt="" width={size} height={size} style={{ display: "block" }} />;
}
