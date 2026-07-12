import { client, unwrap } from "../../../api/http";
import { useApiQuery } from "../../../api/hooks";
import { QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { Prose, PublicPageHeader } from "./shared";

type FAQOut = components["schemas"]["FAQOut"];

export function PublicFaq() {
  const query = useApiQuery(["public", "faqs"], () =>
    unwrap(client.GET("/api/startpage/public/faqs")),
  );

  return (
    <div>
      <PublicPageHeader title="Häufige Fragen" />
      <QueryBoundary query={query} empty="Es sind noch keine Fragen hinterlegt.">
        {(faqs: FAQOut[]) => (
          <div className="stack">
            {faqs.map((faq) => (
              <section key={faq.id}>
                <h2 style={{ marginBottom: "0.25rem" }}>{faq.question}</h2>
                <Prose text={faq.answer} />
              </section>
            ))}
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}
