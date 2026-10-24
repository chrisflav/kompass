import { Route } from "react-router-dom";

import { EmailAddressDetailPage, EmailAddressesList } from "./addresses";
import { MessageComposePage, MessageDetailPage, MessagesList } from "./messages";

// Mailer surface: Nachrichten (Message) list/detail + submit action +
// attachments; E-Mail-Adressen (EmailAddress) list/detail/edit. A message is
// composed on its own page (`/new`, laid out like the detail page so the text
// gets the room and attachments go in directly); an address is created in a
// modal on its list page.
export const mailerRoutes = (
  <>
    <Route path="mailer/messages" element={<MessagesList />} />
    <Route path="mailer/messages/new" element={<MessageComposePage />} />
    <Route path="mailer/messages/:id" element={<MessageDetailPage />} />
    <Route path="mailer/addresses" element={<EmailAddressesList />} />
    <Route path="mailer/addresses/:id" element={<EmailAddressDetailPage />} />
  </>
);
