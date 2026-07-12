import { Route } from "react-router-dom";

import {
  ActivityCategoriesList,
  ActivityCategoryDetailPage,
  TrainingCategoriesList,
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
    <Route path="activity-categories" element={<ActivityCategoriesList />} />
    <Route path="activity-categories/:id" element={<ActivityCategoryDetailPage />} />
    <Route path="training-categories" element={<TrainingCategoriesList />} />
    <Route path="training-categories/:id" element={<TrainingCategoryDetailPage />} />
  </>
);
