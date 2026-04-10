import { redirect } from "next/navigation";
import { publicSiteHref } from "@/lib/public-site";

export default function WhyNotServerlessPageRedirect() {
  redirect(publicSiteHref("/why-not-serverless/"));
}
