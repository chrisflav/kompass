import { useSiteQuery, type Site } from "../../../api/site";
import { QueryBoundary } from "../../../components/ui";
import { PublicPageHeader } from "./shared";

/**
 * The imprint. There is no imprint *content* model — the legally required
 * details are who runs the deployment, which is exactly what the section
 * configuration (`GET /api/startpage/public/site`) holds, so the page is
 * rendered from it rather than from fixed text naming one section.
 *
 * Unlike the chrome, this page renders the query rather than `useSite`'s
 * fallback: an imprint missing its Anschrift and contact details does not
 * satisfy § 5 TMG, and presenting one as though it were complete is worse than
 * saying the data could not be loaded.
 */
export function PublicImpressum() {
  const query = useSiteQuery();
  return (
    <div>
      <PublicPageHeader title="Impressum" />
      <QueryBoundary query={query}>{(site: Site) => <ImpressumBody site={site} />}</QueryBoundary>
    </div>
  );
}

function ImpressumBody({ site }: { site: Site }) {
  return (
    <div className="stack">
      <section>
        <h2>Angaben gemäß § 5 TMG</h2>
        <p>
          {site.display_name}
          <br />
          Jugend des Deutschen Alpenvereins
          {site.dav_section && (
            <>
              <br />
              Sektion {site.dav_section}, Ortsgruppe {site.name}
            </>
          )}
          {site.street && (
            <>
              <br />
              {site.street}
            </>
          )}
          {site.town && (
            <>
              <br />
              {site.town}
            </>
          )}
        </p>
      </section>
      <section>
        <h2>Kontakt</h2>
        {(site.telephone || site.contact_mail) && (
          <p>
            {site.telephone && (
              <>
                Telefon: {site.telephone}
                <br />
              </>
            )}
            {site.contact_mail && <a href={`mailto:${site.contact_mail}`}>{site.contact_mail}</a>}
          </p>
        )}
        <p className="muted">
          Die Kontaktdaten der Jugendleitung findest du auf den jeweiligen Gruppenseiten.
        </p>
      </section>
      <section>
        <h2>Verantwortlich für den Inhalt</h2>
        <p className="muted">Die Jugendleitung der {site.display_name}.</p>
        {site.responsible_mail && (
          <p>
            <a href={`mailto:${site.responsible_mail}`}>{site.responsible_mail}</a>
          </p>
        )}
      </section>
    </div>
  );
}
