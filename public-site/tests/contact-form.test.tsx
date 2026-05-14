import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { ContactForm } from "../components/contact-form";

const FORM_VALUES = {
  name: "Joshua McQueary",
  email: "joshuamcqueary@example.invalid",
  company: "Agent Works Group",
  useCase: "Pilot evaluation",
  message: "Looking to use SparkPilot for AWS Spark needs.",
};

test("contact form renders a native POST to the app contact proxy", () => {
  const html = renderToStaticMarkup(
    <ContactForm
      contactEndpoint="https://app.sparkpilot.cloud/api/contact"
      errorMessage={null}
      form={FORM_VALUES}
      formToken="signed-contact-token"
      onChange={() => undefined}
      onSubmit={() => undefined}
      state="idle"
    />,
  );

  const formTag = html.match(/<form\b[^>]*>/)?.[0] ?? "";
  assert.match(formTag, /action="https:\/\/app\.sparkpilot\.cloud\/api\/contact"/);
  assert.match(formTag, /method="post"/);
  assert.match(html, /name="formToken" value="signed-contact-token"/);
  assert.match(html, /name="website"/);
  assert.doesNotMatch(html, /api\.sparkpilot\.cloud/);
  assert.doesNotMatch(html, /\/v1\/public\/contact/);
});
