import { Route } from "react-router-dom";

import { FeedbackDetailPage, FeedbackList } from "./Feedback";
import { PermissionGroupDetailPage, PermissionGroupsList } from "./PermissionGroups";
import { RegistrationPasswordsList } from "./RegistrationPasswords";
import { UserDetailPage, UsersList } from "./Users";

// The `logindata` app: Django users, permission groups and the shared
// registration password. Previously the only admin area with no SPA counterpart,
// which forced administrators back into /kompass for these three models.
// Plus the feedback inbox, whose submissions arrive from the button in the site
// chrome — public visitors included.
export const adminRoutes = (
  <>
    <Route path="users" element={<UsersList />} />
    <Route path="users/:id" element={<UserDetailPage />} />

    <Route path="permission-groups" element={<PermissionGroupsList />} />
    <Route path="permission-groups/:id" element={<PermissionGroupDetailPage />} />

    <Route path="registration-passwords" element={<RegistrationPasswordsList />} />

    <Route path="feedback" element={<FeedbackList />} />
    <Route path="feedback/:id" element={<FeedbackDetailPage />} />
  </>
);
