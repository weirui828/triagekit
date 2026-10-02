import Link from "next/link";
const items = [["/datasets", "Datasets"], ["/label", "Label"], ["/train", "Train"], ["/triage", "Triage"], ["/monitor", "Monitor"]] as const;
export function Nav() {
  return (
    <nav className="nav">
      <Link href="/" className="brand">triagekit</Link>
      {items.map(([href, label]) => <Link key={href} href={href}>{label}</Link>)}
    </nav>
  );
}
