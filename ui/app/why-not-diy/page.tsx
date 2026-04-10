import { redirect } from "next/navigation";
import { publicSiteHref } from "@/lib/public-site";

export default function WhyNotDiyPageRedirect() {
  redirect(publicSiteHref("/why-not-diy/"));
}
