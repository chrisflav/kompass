import { Navigate, Route, useParams } from "react-router-dom";

import { CartLayout } from "./cart";
import { Catalogue } from "./Catalogue";
import { CategoriesList, CategoryDetailPage } from "./categories";
import { Desk } from "./Desk";
import { Deficits, Locations } from "./Lists";
import { Mine } from "./Mine";
import { PartDetailPage } from "./PartDetail";
import { Psa } from "./Psa";
import { Stock } from "./Stock";
import { TypeDetailPage } from "./TypeDetail";

/** Old part links (`/kompass/material/12`) lead to the piece. */
function LegacyPartRedirect() {
  const { id } = useParams();
  return <Navigate to={`/kompass/material/parts/${id}`} replace />;
}

// Material: the browser with its cart; my material, with the requests for my
// groups; the desk; and the Bestand (pieces with batch hand-over, the PSA
// register, the wishlist, locations and tags, one tab each). Every page
// shares one cart (CartLayout). Requests used to have a page of their own.
export const materialRoutes = (
  <Route path="material" element={<CartLayout />}>
    <Route index element={<Catalogue />} />
    <Route path="types/:id" element={<TypeDetailPage />} />
    <Route path="parts/:id" element={<PartDetailPage />} />
    <Route path="mine" element={<Mine />} />
    <Route path="requests" element={<Navigate to="/kompass/material/mine" replace />} />
    <Route path="desk" element={<Desk />} />
    <Route path="stock" element={<Stock />} />
    <Route path="psa" element={<Psa />} />
    <Route path="deficits" element={<Deficits />} />
    <Route path="locations" element={<Locations />} />
    <Route path="categories" element={<CategoriesList />} />
    <Route path="categories/:id" element={<CategoryDetailPage />} />
    <Route path=":id" element={<LegacyPartRedirect />} />
  </Route>
);
