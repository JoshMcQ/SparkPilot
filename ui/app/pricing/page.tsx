import { redirect } from "next/navigation";
import { publicSiteHref } from "@/lib/public-site";

export default function PricingPageRedirect() {
  redirect(publicSiteHref("/pricing/"));
}
