import { PublicPageHeader } from "./shared";

/**
 * Static imprint page. The backend exposes no imprint endpoint, so this renders
 * fixed contact text (mirroring the legacy static ``impressum`` template).
 */
export function PublicImpressum() {
  return (
    <div>
      <PublicPageHeader title="Impressum" />
      <div className="stack">
        <section>
          <h2>Angaben gemäß § 5 TMG</h2>
          <p>
            JDAV Ludwigsburg
            <br />
            Jugend des Deutschen Alpenvereins
            <br />
            Sektion Schwaben, Ortsgruppe Ludwigsburg
          </p>
        </section>
        <section>
          <h2>Kontakt</h2>
          <p className="muted">
            Die Kontaktdaten der Jugendleitung findest du auf den jeweiligen Gruppenseiten.
          </p>
        </section>
        <section>
          <h2>Verantwortlich für den Inhalt</h2>
          <p className="muted">Die Jugendleitung der JDAV Ludwigsburg.</p>
        </section>
      </div>
    </div>
  );
}
