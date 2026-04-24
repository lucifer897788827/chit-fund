import "./App.css";
import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import LoginPage from "./features/auth/LoginPage";
import ResetPasswordPage from "./features/auth/ResetPasswordPage";
import SignupPage from "./features/auth/SignupPage";
import AuctionRoomPage from "./features/auctions/AuctionRoomPage";
import AdminDashboard from "./features/dashboard/AdminDashboard";
import OwnerDashboard from "./features/dashboard/OwnerDashboard";
import SubscriberDashboard from "./features/dashboard/SubscriberDashboard";
import ExternalChitsPage from "./features/external-chits/ExternalChitsPage";
import NotificationsPage from "./features/notifications/NotificationsPage";
import AdminOwnerRequestsPage from "./features/owner-requests/AdminOwnerRequestsPage";
import { onSessionExpired } from "./lib/auth/session-events";
import { RequireAdmin, RequireAuthenticated, RequireOwner, RequireSubscriber } from "./lib/auth/route-guards";
import { RouteErrorBoundary } from "./components/route-error-boundary";
import SignedInAppShell from "./components/signed-in-shell";
import { Toaster } from "./components/ui/toaster";

function App() {
  const [, setSessionVersion] = useState(0);

  useEffect(() => {
    return onSessionExpired(() => {
      setSessionVersion((currentVersion) => currentVersion + 1);
    });
  }, []);

  return (
    <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <Toaster />
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route
          path="/admin-dashboard"
          element={
            <RouteErrorBoundary>
              <RequireAdmin>
                <SignedInAppShell>
                  <AdminDashboard />
                </SignedInAppShell>
              </RequireAdmin>
            </RouteErrorBoundary>
          }
        />
        <Route
          path="/admin/owner-requests"
          element={
            <RouteErrorBoundary>
              <RequireAdmin>
                <AdminOwnerRequestsPage />
              </RequireAdmin>
            </RouteErrorBoundary>
          }
        />
        <Route
          path="/owner-dashboard"
          element={
            <RouteErrorBoundary>
              <RequireOwner>
                <SignedInAppShell>
                  <OwnerDashboard />
                </SignedInAppShell>
              </RequireOwner>
            </RouteErrorBoundary>
          }
        />
        <Route
          path="/owner"
          element={
            <RouteErrorBoundary>
              <RequireOwner>
                <SignedInAppShell>
                  <OwnerDashboard />
                </SignedInAppShell>
              </RequireOwner>
            </RouteErrorBoundary>
          }
        />
        <Route
          path="/subscriber-dashboard"
          element={
            <RouteErrorBoundary>
              <RequireSubscriber>
                <SignedInAppShell>
                  <SubscriberDashboard />
                </SignedInAppShell>
              </RequireSubscriber>
            </RouteErrorBoundary>
          }
        />
        <Route
          path="/subscriber"
          element={
            <RouteErrorBoundary>
              <RequireSubscriber>
                <SignedInAppShell>
                  <SubscriberDashboard />
                </SignedInAppShell>
              </RequireSubscriber>
            </RouteErrorBoundary>
          }
        />
        <Route
          path="/auctions/:sessionId"
          element={
            <RouteErrorBoundary>
              <RequireSubscriber>
                <SignedInAppShell>
                  <AuctionRoomPage />
                </SignedInAppShell>
              </RequireSubscriber>
            </RouteErrorBoundary>
          }
        />
        <Route
          path="/external-chits"
          element={
            <RouteErrorBoundary>
              <RequireSubscriber>
                <SignedInAppShell>
                  <ExternalChitsPage />
                </SignedInAppShell>
              </RequireSubscriber>
            </RouteErrorBoundary>
          }
        />
        <Route
          path="/notifications"
          element={
            <RouteErrorBoundary>
              <RequireAuthenticated>
                <SignedInAppShell>
                  <NotificationsPage />
                </SignedInAppShell>
              </RequireAuthenticated>
            </RouteErrorBoundary>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
