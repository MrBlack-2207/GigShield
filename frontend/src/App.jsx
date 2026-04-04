import { Navigate, Route, Routes } from "react-router-dom";

import ClaimsTimelinePage from "./pages/ClaimsTimelinePage";
import DashboardPage from "./pages/DashboardPage";
import OnboardingPage from "./pages/OnboardingPage";
import PolicyPurchasePage from "./pages/PolicyPurchasePage";
import WalletPage from "./pages/WalletPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<OnboardingPage />} />
      <Route path="/policy" element={<PolicyPurchasePage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/claims" element={<ClaimsTimelinePage />} />
      <Route path="/wallet" element={<WalletPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
