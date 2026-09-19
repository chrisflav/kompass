import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { AuthProvider } from "./auth";
import { ConfirmProvider, ToastProvider } from "./components/ui";
import { AppRoutes } from "./routes";
// Self-hosted IBM Plex (GDPR-safe: no external font requests). Sans carries the
// body/display voice; Mono is the "instrument" utility face for labels, ids and
// tabular figures.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
// KaTeX math styling for Markdown posts (fonts bundled by Vite, no CDN).
import "katex/dist/katex.min.css";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => {
        // Never retry auth/permission/not-found — only transient failures.
        const status = (error as { status?: number })?.status;
        if (status && [401, 403, 404, 422].includes(status)) return false;
        return count < 2;
      },
      staleTime: 30_000,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ToastProvider>
          <ConfirmProvider>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </ConfirmProvider>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
