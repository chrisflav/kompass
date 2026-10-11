import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { PublicLayout } from "./components/Layout";
import { NotFound } from "./components/Placeholder";
import { Spinner } from "./components/ui";
import { AuthCallback, Login } from "./pages/Login";
import {
  legacyRedirectRoutes,
  publicFlowRoutes,
  publicSiteRoutes,
} from "./features/public/routes";

// The workspace is most of the code and none of the public site's, so it is
// fetched only once someone opens it.
const KompassRoutes = lazy(() => import("./kompassRoutes"));

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/callback" element={<AuthCallback />} />

      {/* Authenticated administration app. */}
      <Route
        path="/kompass/*"
        element={
          <Suspense fallback={<Spinner />}>
            <KompassRoutes />
          </Suspense>
        }
      />

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
