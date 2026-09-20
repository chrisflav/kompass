import { useSite } from "../../../api/site";
import { PublicPageHeader } from "./shared";

/**
 * The imprint. There is no imprint *content* model — the legally required
 * details are who runs the deployment, which is exactly what the section
 * configuration (`GET /api/startpage/public/site`) holds, so the page is
 * rendered from it rather than from fixed text naming one section.
 */
export function PublicImpressum() {
  const site = useSite();
  return (
    <div>
      <PublicPageHeader title="Impressum" />
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
          <p>
            {site.telephone && (
              <>
                Telefon: {site.telephone}
                <br />
              </>
            )}
            {site.contact_mail && (
              <a href={`mailto:${site.contact_mail}`}>{site.contact_mail}</a>
            )}
          </p>
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
    </div>
  );
}
