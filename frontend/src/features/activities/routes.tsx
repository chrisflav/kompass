import { Route } from "react-router-dom";

import {
  ActivityCategoryDetailPage,
  CategoriesPage,
  TrainingCategoryDetailPage,
} from "./Categories";
import { ExcursionDetailPage, ExcursionsList } from "./Excursions";
import { GroupDetailPage, GroupsList } from "./Groups";
import { KlettertreffDetailPage, KlettertreffList } from "./Klettertreff";
import { NoteListDetailPage, NoteListsList } from "./NoteLists";

export const activitiesRoutes = (
  <>
    <Route path="groups" element={<GroupsList />} />
    <Route path="groups/:id" element={<GroupDetailPage />} />
    <Route path="excursions" element={<ExcursionsList />} />
    <Route path="excursions/:id" element={<ExcursionDetailPage />} />
    <Route path="klettertreff" element={<KlettertreffList />} />
    <Route path="klettertreff/:id" element={<KlettertreffDetailPage />} />
    <Route path="notelists" element={<NoteListsList />} />
    <Route path="notelists/:id" element={<NoteListDetailPage />} />
    <Route path="categories" element={<CategoriesPage />} />
    <Route path="categories/activity/:id" element={<ActivityCategoryDetailPage />} />
    <Route path="categories/training/:id" element={<TrainingCategoryDetailPage />} />
  </>
);
