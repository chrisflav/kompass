import { Route } from "react-router-dom";

import { EmailAddressDetailPage, EmailAddressesList } from "./addresses";
import { MessageDetailPage, MessagesList } from "./messages";

// Mailer surface: Nachrichten (Message) list/detail + submit action +
// attachments; E-Mail-Adressen (EmailAddress) list/detail/edit. Creating a
// message or an address happens in a modal on the respective list page.
export const mailerRoutes = (
  <>
    <Route path="mailer/messages" element={<MessagesList />} />
    <Route path="mailer/messages/:id" element={<MessageDetailPage />} />
    <Route path="mailer/addresses" element={<EmailAddressesList />} />
    <Route path="mailer/addresses/:id" element={<EmailAddressDetailPage />} />
  </>
);
