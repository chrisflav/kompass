import { Route } from "react-router-dom";

import { PostDetailPage, PostsList } from "./PostRoutes";
import { SectionDetailPage, SectionsList } from "./SectionRoutes";
import { FaqDetailPage, FaqList } from "./FaqRoutes";
import { LinkDetailPage, LinksList } from "./LinkRoutes";

// Phase C (cms): startpage content CRUD — Beiträge (Post), Bereiche (Section),
// FAQ, Links. Each list/detail/edit/delete against /api/startpage/*; create via
// modal on the respective list page.
export const cmsRoutes = (
  <>
    <Route path="cms/posts" element={<PostsList />} />
    <Route path="cms/posts/:id" element={<PostDetailPage />} />

    <Route path="cms/sections" element={<SectionsList />} />
    <Route path="cms/sections/:id" element={<SectionDetailPage />} />

    <Route path="cms/faqs" element={<FaqList />} />
    <Route path="cms/faqs/:id" element={<FaqDetailPage />} />

    <Route path="cms/links" element={<LinksList />} />
    <Route path="cms/links/:id" element={<LinkDetailPage />} />
  </>
);
