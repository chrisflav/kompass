import { useParams } from "react-router-dom";

import { client, unwrap } from "../../../api/http";
import { useApiQuery } from "../../../api/hooks";
import { QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { Prose, PublicPageHeader } from "./shared";

type SectionOut = components["schemas"]["SectionOut"];

export function PublicSection() {
  const { section } = useParams();
  const sectionName = section ?? "";
  const query = useApiQuery(["public", "section", sectionName], () =>
    unwrap(
      client.GET("/api/startpage/public/sections/{section_name}", {
        params: { path: { section_name: sectionName } },
      }),
    ),
  );

  return (
    <div>
      <QueryBoundary query={query}>
        {(data: SectionOut) => (
          <>
            <PublicPageHeader title={data.title} />
            <Prose text={data.website_text} />
          </>
        )}
      </QueryBoundary>
    </div>
  );
}
