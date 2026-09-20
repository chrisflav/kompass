import { Navigate, Route, useLocation } from "react-router-dom";

import { PublicIndex } from "./site/Index";
import { PublicAktuelles, PublicBerichte } from "./site/SectionPosts";
import { PublicGruppen } from "./site/Gruppen";
import { PublicGruppeDetail } from "./site/GruppeDetail";
import { PublicFaq } from "./site/Faq";
import { PublicImpressum } from "./site/Impressum";
import { PublicSection } from "./site/Section";
import { PublicPost } from "./site/Post";

import { EchoFlow } from "./flows/Echo";
import { RegisterFlow } from "./flows/Register";
import { InvitedRegistrationFlow } from "./flows/InvitedRegistration";
import { UploadFormFlow } from "./flows/UploadForm";
import { WaitingListFlow } from "./flows/WaitingList";
import { ConfirmWaitingFlow } from "./flows/ConfirmWaiting";
import { LeaveWaitingListFlow } from "./flows/LeaveWaitingList";
import { ConfirmInvitationFlow } from "./flows/ConfirmInvitation";
import { RejectInvitationFlow } from "./flows/RejectInvitation";
import { ConfirmMailFlow } from "./flows/ConfirmMail";
import { UnsubscribeFlow } from "./flows/Unsubscribe";
import { PasswordFlow } from "./flows/Password";
import { SubmitTerminFlow } from "./flows/SubmitTermin";

// Public website rendered from /api/startpage/public/* inside <PublicLayout>.
export const publicSiteRoutes = (
  <>
    <Route index element={<PublicIndex />} />
    <Route path="aktuelles" element={<PublicAktuelles />} />
    <Route path="berichte" element={<PublicBerichte />} />
    <Route path="gruppen" element={<PublicGruppen />} />
    <Route path="gruppen/faq" element={<PublicFaq />} />
    <Route path="gruppe/:name" element={<PublicGruppeDetail />} />
    <Route path="impressum" element={<PublicImpressum />} />
    <Route path="bereich/:section" element={<PublicSection />} />
    <Route path="beitrag/:section/:post" element={<PublicPost />} />
  </>
);

/** Redirects the pre-SPA Django URLs to their new SPA flow, preserving the
 *  ``?key=`` query string. Keeps old bookmarked / e-mailed links working. */
function LegacyRedirect({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}

// Old Django path (under /members, /newsletter, /login) → new SPA path.
const LEGACY_FLOW_PATHS: [string, string][] = [
  ["members/echo", "/echo"],
  ["members/registration", "/anmeldung"],
  ["members/register/upload", "/anmeldebogen"],
  // The old download-form step is replaced by the upload page in the SPA.
  ["members/register/download", "/anmeldebogen"],
  ["members/register", "/registrierung"],
  ["members/waitinglist/confirm", "/warteliste/bestaetigen"],
  ["members/waitinglist/leave", "/warteliste/verlassen"],
  ["members/waitinglist/invitation/confirm", "/einladung/annehmen"],
  ["members/waitinglist/invitation/reject", "/einladung/ablehnen"],
  ["members/waitinglist", "/warteliste"],
  ["members/mail/confirm", "/mail/bestaetigen"],
  ["newsletter/unsubscribe", "/abmelden"],
  ["login/register", "/passwort"],
];

// Both the bare path and the German locale-prefixed variant (old URLs lived
// inside Django's i18n_patterns, so real links carry a `/de/` prefix).
export const legacyRedirectRoutes = (
  <>
    {LEGACY_FLOW_PATHS.flatMap(([from, to]) => [
      <Route key={from} path={from} element={<LegacyRedirect to={to} />} />,
      <Route key={`de/${from}`} path={`de/${from}`} element={<LegacyRedirect to={to} />} />,
    ])}
  </>
);

// Standalone secret-key self-service flows (auth=None API), no site chrome.
export const publicFlowRoutes = (
  <>
    <Route path="echo" element={<EchoFlow />} />
    <Route path="registrierung" element={<RegisterFlow />} />
    <Route path="anmeldung" element={<InvitedRegistrationFlow />} />
    <Route path="anmeldebogen" element={<UploadFormFlow />} />
    <Route path="warteliste" element={<WaitingListFlow />} />
    <Route path="warteliste/bestaetigen" element={<ConfirmWaitingFlow />} />
    <Route path="warteliste/verlassen" element={<LeaveWaitingListFlow />} />
    <Route path="einladung/annehmen" element={<ConfirmInvitationFlow />} />
    <Route path="einladung/ablehnen" element={<RejectInvitationFlow />} />
    <Route path="mail/bestaetigen" element={<ConfirmMailFlow />} />
    <Route path="abmelden" element={<UnsubscribeFlow />} />
    <Route path="passwort" element={<PasswordFlow />} />
    <Route path="termin-einreichen" element={<SubmitTerminFlow />} />
  </>
);
