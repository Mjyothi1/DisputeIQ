import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { CaseDetailPage } from "@/pages/CaseDetailPage";
import { ComplaintDetailPage } from "@/pages/customer/ComplaintDetailPage";
import { CustomerAuthPage } from "@/pages/customer/CustomerAuthPage";
import { CustomerVerifyEmailPage } from "@/pages/customer/CustomerVerifyEmailPage";
import { CustomerDashboard } from "@/pages/customer/CustomerDashboard";
import { CustomerLayout } from "@/pages/customer/CustomerLayout";
import { ReportProblemPage } from "@/pages/customer/ReportProblemPage";
import { LandingPage } from "@/pages/LandingPage";
import { MetricsPage } from "@/pages/MetricsPage";
import { QueuePage } from "@/pages/QueuePage";
import { SubmitPage } from "@/pages/SubmitPage";

function LegacyCase() {
  return <Navigate to={`/reviewer/cases/${useParams().id}`} replace />;
}

const notFound = <p className="py-10 text-center text-muted-foreground">Page not found.</p>;

export function App() {
  return (
    <Routes>
      <Route index element={<LandingPage />} />
      <Route path="customer/login" element={<CustomerAuthPage mode="login" />} />
      <Route path="customer/register" element={<CustomerAuthPage mode="register" />} />
      <Route path="customer/verify-email" element={<CustomerVerifyEmailPage />} />
      <Route path="customer" element={<CustomerLayout />}>
        <Route index element={<CustomerDashboard />} />
        <Route path="report" element={<ReportProblemPage />} />
        <Route path="complaints/:id" element={<ComplaintDetailPage />} />
        <Route path="*" element={notFound} />
      </Route>
      <Route path="reviewer" element={<Layout />}>
        <Route index element={<QueuePage />} />
        <Route path="cases/:id" element={<CaseDetailPage />} />
        <Route path="submit" element={<SubmitPage />} />
        <Route path="metrics" element={<MetricsPage />} />
        <Route path="*" element={notFound} />
      </Route>
      {/* old reviewer links keep working */}
      <Route path="cases/:id" element={<LegacyCase />} />
      <Route path="submit" element={<Navigate to="/reviewer/submit" replace />} />
      <Route path="metrics" element={<Navigate to="/reviewer/metrics" replace />} />
      <Route path="*" element={notFound} />
    </Routes>
  );
}
