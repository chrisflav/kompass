import { Route } from "react-router-dom";

import { BillDetailPage, BillsList } from "./Bills";
import { LedgerDetailPage, LedgersList } from "./Ledgers";
import { StatementDetailPage, StatementsList } from "./Statements";
import { StatementFlowPage } from "./StatementFlow";
import { StatementReviewPage } from "./StatementReview";
import { TransactionDetailPage, TransactionsList } from "./Transactions";

// Finance surface. A statement is worked through two guided routes rather than
// its raw fields: `/new` + `/:id/edit` is the leader's submission flow
// (?stage=purpose → receipts → reimbursement → submit, ending in a handed-in
// statement or a saved draft), and `/:id/review` is the treasurer's review
// pipeline (?stage=expenses → bookings → payout). `/:id` stays the record view
// for everything else — full fieldsets, inlines and the summary PDF. Plus Belege
// (Bill) list/detail/create incl. proof upload; Buchungen (Transaction, read
// only); Konten (Ledger) CRUD.
export const financeRoutes = (
  <>
    <Route path="finance/statements" element={<StatementsList />} />
    <Route path="finance/statements/new" element={<StatementFlowPage />} />
    <Route path="finance/statements/:id" element={<StatementDetailPage />} />
    <Route path="finance/statements/:id/edit" element={<StatementFlowPage />} />
    <Route path="finance/statements/:id/review" element={<StatementReviewPage />} />
    <Route path="finance/bills" element={<BillsList />} />
    <Route path="finance/bills/:id" element={<BillDetailPage />} />
    <Route path="finance/transactions" element={<TransactionsList />} />
    <Route path="finance/transactions/:id" element={<TransactionDetailPage />} />
    <Route path="finance/ledgers" element={<LedgersList />} />
    <Route path="finance/ledgers/:id" element={<LedgerDetailPage />} />
  </>
);
