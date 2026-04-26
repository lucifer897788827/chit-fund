import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { PageLoadingState } from "../../components/page-state";
import { fetchCurrentUser } from "../../features/auth/api";
import { getCurrentUser, getUserRoles, sessionHasRole, updateSession } from "./store";

function hasMemberAccess(session) {
  const roles = getUserRoles(session);
  return roles.includes("subscriber") || roles.includes("owner");
}

function hasOwnerAccess(session) {
  return sessionHasRole(session, "owner") || Boolean(session?.owner_id ?? session?.ownerId);
}

function hasAdminAccess(session) {
  return sessionHasRole(session, "admin");
}

function RoleRoute({ children, canAccess, redirectTo = "/" }) {
  const location = useLocation();
  const [state, setState] = useState(() => ({
    loading: Boolean(getCurrentUser()?.access_token),
    session: getCurrentUser(),
  }));

  useEffect(() => {
    let active = true;
    const storedSession = getCurrentUser();

    if (!storedSession?.access_token) {
      setState({ loading: false, session: null });
      return () => {
        active = false;
      };
    }

    setState({ loading: true, session: storedSession });
    fetchCurrentUser()
      .then((authState) => {
        if (active) {
          setState({ loading: false, session: updateSession(authState) });
        }
      })
      .catch(() => {
        if (active) {
          setState({ loading: false, session: getCurrentUser() });
        }
      });

    return () => {
      active = false;
    };
  }, [location.pathname]);

  if (state.loading) {
    return (
      <main className="page-shell">
        <PageLoadingState description="Checking your account access." label="Loading workspace..." />
      </main>
    );
  }

  if (!state.session?.access_token || !canAccess(state.session)) {
    return <Navigate replace state={{ from: location }} to={redirectTo} />;
  }

  return children;
}

export function MemberRoute({ children }) {
  return <RoleRoute canAccess={hasMemberAccess}>{children}</RoleRoute>;
}

export function OwnerRoute({ children }) {
  return <RoleRoute canAccess={hasOwnerAccess} redirectTo="/home">{children}</RoleRoute>;
}

export function AdminRoute({ children }) {
  return <RoleRoute canAccess={hasAdminAccess} redirectTo="/home">{children}</RoleRoute>;
}

export const RequireAuthenticated = MemberRoute;
export const RequireSubscriber = MemberRoute;
export const RequireOwner = OwnerRoute;
export const RequireAdmin = AdminRoute;

export function canAccessAuthenticatedRoutes(currentUser) {
  return hasMemberAccess(currentUser);
}

export function canAccessSubscriberRoutes(currentUser) {
  return hasMemberAccess(currentUser);
}

export function canAccessOwnerRoutes(currentUser) {
  return hasOwnerAccess(currentUser);
}

export function canAccessAdminRoutes(currentUser) {
  return hasAdminAccess(currentUser);
}
