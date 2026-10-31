import { Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { CaseDetailPage } from "@/pages/CaseDetailPage";
import { MetricsPage } from "@/pages/MetricsPage";
import { QueuePage } from "@/pages/QueuePage";
import { SubmitPage } from "@/pages/SubmitPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<QueuePage />} />
        <Route path="cases/:id" element={<CaseDetailPage />} />
        <Route path="submit" element={<SubmitPage />} />
        <Route path="metrics" element={<MetricsPage />} />
        <Route
          path="*"
          element={<p className="py-10 text-center text-muted-foreground">Page not found.</p>}
        />
      </Route>
    </Routes>
  );
}
