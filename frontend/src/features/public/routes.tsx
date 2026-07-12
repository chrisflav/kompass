import { Route } from "react-router-dom";

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
