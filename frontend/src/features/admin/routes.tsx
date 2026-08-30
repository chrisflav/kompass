import { Route } from "react-router-dom";

import { PermissionGroupDetailPage, PermissionGroupsList } from "./PermissionGroups";
import { RegistrationPasswordsList } from "./RegistrationPasswords";
import { UserDetailPage, UsersList } from "./Users";

// The `logindata` app: Django users, permission groups and the shared
// registration password. Previously the only admin area with no SPA counterpart,
// which forced administrators back into /kompass for these three models.
export const adminRoutes = (
  <>
    <Route path="users" element={<UsersList />} />
    <Route path="users/:id" element={<UserDetailPage />} />

    <Route path="permission-groups" element={<PermissionGroupsList />} />
    <Route path="permission-groups/:id" element={<PermissionGroupDetailPage />} />

    <Route path="registration-passwords" element={<RegistrationPasswordsList />} />
  </>
);
