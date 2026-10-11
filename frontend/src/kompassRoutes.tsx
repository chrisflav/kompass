import { Route, Routes } from "react-router-dom";

import { AppLayout, ProtectedRoute } from "./components/Layout";
import { NotFound } from "./components/Placeholder";
import { Dashboard } from "./pages/Dashboard";
import { activitiesRoutes } from "./features/activities/routes";
import { adminRoutes } from "./features/admin/routes";
import { cmsRoutes } from "./features/cms/routes";
import { eventsRoutes } from "./features/events/routes";
import { financeRoutes } from "./features/finance/routes";
import { mailerRoutes } from "./features/mailer/routes";
import { materialRoutes } from "./features/material/routes";
import { membersRoutes } from "./features/members/routes";

/**
 * The authenticated administration app, everything under /kompass.
 *
 * Its own module so that routes.tsx can load it lazily: a visitor of the public
 * site never downloads the workspace, which is most of the application code.
 * The paths here are relative to the `/kompass/*` route that mounts it.
 */
export default function KompassRoutes() {
  return (
    <Routes>
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        {membersRoutes}
        {activitiesRoutes}
        {financeRoutes}
        {mailerRoutes}
        {materialRoutes}
        {eventsRoutes}
        {cmsRoutes}
        {adminRoutes}
      </Route>
      {/* An unknown workspace path answers as it did before the split: the bare
          not-found page, without the guard or the chrome. */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
