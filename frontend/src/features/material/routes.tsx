import { Route } from "react-router-dom";

import { CategoriesList, CategoryDetailPage } from "./categories";
import { PartDetailPage, PartsList } from "./parts";

// Material surface: Material (MaterialPart) list/detail/edit incl. photo upload;
// Materialkategorien (MaterialCategory) list/detail/edit. Creating a part or a
// category happens in a modal on the respective list page.
export const materialRoutes = (
  <>
    <Route path="material" element={<PartsList />} />
    <Route path="material/categories" element={<CategoriesList />} />
    <Route path="material/categories/:id" element={<CategoryDetailPage />} />
    <Route path="material/:id" element={<PartDetailPage />} />
  </>
);
