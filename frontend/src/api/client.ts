import createClient from "openapi-fetch";

import { getToken } from "../auth";
import type { paths } from "./schema";

// Backend origin. Override with VITE_API_BASE when the API is elsewhere.
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export const client = createClient<paths>({ baseUrl: API_BASE });

// Attach the bearer token (if any) to every request.
client.use({
  onRequest({ request }) {
    const token = getToken();
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
});
