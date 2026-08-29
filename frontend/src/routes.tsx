import { Route, Routes } from "react-router-dom";

import { AppLayout, ProtectedRoute, PublicLayout } from "./components/Layout";
import { NotFound } from "./components/Placeholder";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { activitiesRoutes } from "./features/activities/routes";
import { cmsRoutes } from "./features/cms/routes";
import { eventsRoutes } from "./features/events/routes";
import { financeRoutes } from "./features/finance/routes";
import { mailerRoutes } from "./features/mailer/routes";
import { materialRoutes } from "./features/material/routes";
import { membersRoutes } from "./features/members/routes";
import {
  legacyRedirectRoutes,
  publicFlowRoutes,
  publicSiteRoutes,
} from "./features/public/routes";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      {/* Authenticated administration app. */}
      <Route
        path="/app"
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
      </Route>

      {/* Redirects from the old Django URLs to the new SPA flows. */}
      {legacyRedirectRoutes}

      {/* Standalone public secret-key flows (no site chrome). */}
      {publicFlowRoutes}

      {/* Public website. */}
      <Route path="/" element={<PublicLayout />}>
        {publicSiteRoutes}
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
