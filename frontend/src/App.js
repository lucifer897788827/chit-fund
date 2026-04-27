import "./App.css";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AppShell from "./components/app-shell";
import { RouteErrorBoundary } from "./components/route-error-boundary";
import { Toaster } from "./components/ui/toaster";
import AuctionRoomPage from "./features/auctions/AuctionRoomPage";
import LoginPage from "./features/auth/LoginPage";
import ResetPasswordPage from "./features/auth/ResetPasswordPage";
import SignupPage from "./features/auth/SignupPage";
import ExternalChitsPage from "./features/external-chits/ExternalChitsPage";
import NotificationsPage from "./features/notifications/NotificationsPage";
import { AdminRoute, MemberRoute, OwnerRoute } from "./lib/auth/route-guards";
import { queryClient } from "./lib/query-client";
import ActionsPage from "./pages/ActionsPage";
import CreateGroupPage from "./pages/CreateGroupPage";
import GroupDetailPage from "./pages/GroupDetailPage";
import GroupsListPage from "./pages/GroupsListPage";
import HomePage from "./pages/HomePage";
import PaymentsPage from "./pages/PaymentsPage";
import ProfilePage from "./pages/ProfilePage";
import AdminGroupDetailPage from "./pages/admin/AdminGroupDetailPage";
import AdminAuctionsPage from "./pages/admin/AdminAuctionsPage";
import AdminGroupsPage from "./pages/admin/AdminGroupsPage";
import AdminHomePage from "./pages/admin/AdminHomePage";
import AdminPaymentsPage from "./pages/admin/AdminPaymentsPage";
import BroadcastPage from "./pages/admin/BroadcastPage";
import OwnerRequestsPage from "./pages/admin/OwnerRequestsPage";
import SystemPage from "./pages/admin/SystemPage";
import UserDetailPage from "./pages/admin/UserDetailPage";
import UsersPage from "./pages/admin/UsersPage";

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <Toaster />
        <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        <Route
          element={
            <RouteErrorBoundary>
              <MemberRoute>
                <AppShell />
              </MemberRoute>
            </RouteErrorBoundary>
          }
        >
          <Route path="/home" element={<HomePage />} />
          <Route path="/groups" element={<GroupsListPage />} />
          <Route
            path="/groups/create"
            element={
              <OwnerRoute>
                <CreateGroupPage />
              </OwnerRoute>
            }
          />
          <Route path="/groups/:groupId" element={<GroupDetailPage />} />
          <Route path="/payments" element={<PaymentsPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/external-chits" element={<ExternalChitsPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route
            path="/actions"
            element={
              <OwnerRoute>
                <ActionsPage />
              </OwnerRoute>
            }
          />
          <Route path="/auctions/:sessionId" element={<AuctionRoomPage />} />
        </Route>

        <Route
          element={
            <RouteErrorBoundary>
              <AdminRoute>
                <AppShell />
              </AdminRoute>
            </RouteErrorBoundary>
          }
        >
          <Route path="/admin" element={<AdminHomePage />} />
          <Route path="/admin/owner-requests" element={<OwnerRequestsPage />} />
          <Route path="/admin/users" element={<UsersPage />} />
          <Route path="/admin/users/:id" element={<UserDetailPage />} />
              <Route path="/admin/groups" element={<AdminGroupsPage />} />
              <Route path="/admin/groups/:id" element={<AdminGroupDetailPage />} />
              <Route path="/admin/auctions" element={<AdminAuctionsPage />} />
              <Route path="/admin/payments" element={<AdminPaymentsPage />} />
              <Route path="/admin/system" element={<SystemPage />} />
              <Route path="/admin/broadcast" element={<BroadcastPage />} />
        </Route>

        <Route path="/owner" element={<Navigate replace to="/home" />} />
        <Route path="/owner-dashboard" element={<Navigate replace to="/home" />} />
        <Route path="/subscriber" element={<Navigate replace to="/home" />} />
        <Route path="/subscriber-dashboard" element={<Navigate replace to="/home" />} />
        <Route path="/admin-dashboard" element={<Navigate replace to="/admin" />} />
        <Route path="*" element={<Navigate replace to="/" />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
