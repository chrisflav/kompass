import { Route } from "react-router-dom";

import { BillDetailPage, BillsList } from "./Bills";
import { LedgerDetailPage, LedgersList } from "./Ledgers";
import { StatementDetailPage, StatementsList } from "./Statements";
import { TransactionDetailPage, TransactionsList } from "./Transactions";

// Finance surface: Abrechnungen (Statement) list/detail/create + state-machine
// actions (submit/generate/reduce/confirm/reject/unconfirm) + summary PDF;
// Belege (Bill) list/detail/create incl. proof upload; Buchungen (Transaction,
// read only); Konten (Ledger) list/detail/create/edit/delete.
export const financeRoutes = (
  <>
    <Route path="finance/statements" element={<StatementsList />} />
    <Route path="finance/statements/:id" element={<StatementDetailPage />} />
    <Route path="finance/bills" element={<BillsList />} />
    <Route path="finance/bills/:id" element={<BillDetailPage />} />
    <Route path="finance/transactions" element={<TransactionsList />} />
    <Route path="finance/transactions/:id" element={<TransactionDetailPage />} />
    <Route path="finance/ledgers" element={<LedgersList />} />
    <Route path="finance/ledgers/:id" element={<LedgerDetailPage />} />
  </>
);
