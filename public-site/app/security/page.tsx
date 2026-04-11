import { redirect } from "next/navigation";

export default function SecurityPageRedirect() {
  redirect("/contact");
}

