import Link from "next/link";
export default function NotFound() {
  return (
    <div className="card" style={{padding: "2rem"}}>
      <h2>Page not found</h2>
      <Link href="/" className="button">Go home</Link>
    </div>
  );
}
