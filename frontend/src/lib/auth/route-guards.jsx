import { Navigate } from "react-router-dom";

import { getCurrentUser, sessionHasRole } from "./store";

function getOwnerId(currentUser) {
  return currentUser?.owner_id ?? currentUser?.ownerId ?? null;
}

function getSubscriberId(currentUser) {
  return currentUser?.subscriber_id ?? currentUser?.subscriberId ?? null;
}

function hasSubscriberProfile(currentUser) {
  return Boolean(currentUser?.has_subscriber_profile ?? currentUser?.hasSubscriberProfile);
}

function Guard({ children, canAccess }) {
  const currentUser = getCurrentUser();

  if (!currentUser?.access_token || !canAccess(currentUser)) {
    return <Navigate replace to="/" />;
  }

  return children;
}

export function canAccessOwnerRoutes(currentUser) {
  return sessionHasRole(currentUser, "owner") || Boolean(getOwnerId(currentUser));
}

export function canAccessSubscriberRoutes(currentUser) {
  return sessionHasRole(currentUser, "subscriber") || Boolean(getSubscriberId(currentUser)) || hasSubscriberProfile(currentUser);
}

export function canAccessAuthenticatedRoutes(currentUser) {
  return Boolean(currentUser?.access_token);
}

export function canAccessAdminRoutes(currentUser) {
  return sessionHasRole(currentUser, "admin");
}

export function RequireOwner({ children }) {
  return <Guard canAccess={canAccessOwnerRoutes}>{children}</Guard>;
}

export function RequireSubscriber({ children }) {
  return <Guard canAccess={canAccessSubscriberRoutes}>{children}</Guard>;
}

export function RequireAuthenticated({ children }) {
  return <Guard canAccess={canAccessAuthenticatedRoutes}>{children}</Guard>;
}

export function RequireAdmin({ children }) {
  return <Guard canAccess={canAccessAdminRoutes}>{children}</Guard>;
}
