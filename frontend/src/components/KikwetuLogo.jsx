import kikwetuLogo from "../assets/kikwetu-eggs-logo.png";

export default function KikwetuLogo({ size = "small", className = "" }) {
  const classes = ["kikwetu-logo", `kikwetu-logo-${size}`, className]
    .filter(Boolean)
    .join(" ");

  return <img src={kikwetuLogo} alt="Kikwetu Eggs" className={classes} />;
}
