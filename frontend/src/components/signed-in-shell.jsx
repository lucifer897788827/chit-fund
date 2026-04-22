import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Bell, CreditCard, Gavel, Home, UserRound } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { getCurrentUser } from "../lib/auth/store";

const SignedInShellContext = createContext(null);

function formatRoleLabel(role) {
  if (role === "chit_owner") {
    return "Chit owner";
  }
  if (role === "subscriber") {
    return "Subscriber";
  }
  return "Signed in";
}

function getDashboardPath(currentUser) {
  if (currentUser?.role === "chit_owner" || currentUser?.owner_id || currentUser?.ownerId) {
    return "/owner";
  }
  if (currentUser?.role === "subscriber" || currentUser?.subscriber_id || currentUser?.subscriberId) {
    return "/subscriber";
  }
  return "/";
}

function getDefaultPageMeta(pathname) {
  if (pathname.startsWith("/auctions/")) {
    return {
      title: "Auction room",
      contextLabel: "Live round updates and bidding",
    };
  }
  if (pathname === "/notifications") {
    return {
      title: "Notifications",
      contextLabel: "Auction and payment alerts",
    };
  }
  if (pathname === "/external-chits") {
    return {
      title: "External chits",
      contextLabel: "Private off-platform records",
    };
  }
  if (pathname === "/owner") {
    return {
      title: "Owner dashboard",
      contextLabel: "Groups, auctions, and collections",
    };
  }
  if (pathname === "/subscriber") {
    return {
      title: "Subscriber dashboard",
      contextLabel: "Memberships, dues, and bidding access",
    };
  }
  return {
    title: "Workspace",
    contextLabel: "Manage your chit fund activity",
  };
}

function isNavItemActive(itemKey, pathname, hash) {
  if (itemKey === "home") {
    return (pathname === "/owner" || pathname === "/subscriber") && !hash;
  }
  if (itemKey === "auctions") {
    return pathname.startsWith("/auctions/") || hash === "#auctions";
  }
  if (itemKey === "payments") {
    return hash === "#payments";
  }
  if (itemKey === "notifications") {
    return pathname === "/notifications";
  }
  if (itemKey === "profile") {
    return hash === "#profile";
  }
  return false;
}

export function useSignedInShellHeader({ title, contextLabel }) {
  const setPageMeta = useContext(SignedInShellContext);

  useEffect(() => {
    if (typeof setPageMeta !== "function") {
      return undefined;
    }

    setPageMeta({
      title,
      contextLabel,
    });

    return () => {
      setPageMeta(null);
    };
  }, [contextLabel, setPageMeta, title]);
}

export default function SignedInAppShell({ children }) {
  const currentUser = getCurrentUser();
  const location = useLocation();
  const [pageMeta, setPageMeta] = useState(null);
  const dashboardPath = getDashboardPath(currentUser);
  const roleLabel = formatRoleLabel(currentUser?.role);

  useEffect(() => {
    setPageMeta(null);
  }, [location.pathname]);

  const headerMeta = {
    ...getDefaultPageMeta(location.pathname),
    ...(pageMeta ?? {}),
  };

  const navItems = useMemo(
    () => [
      { key: "home", label: "Home", icon: Home, to: dashboardPath },
      {
        key: "auctions",
        label: "Auctions",
        icon: Gavel,
        to: location.pathname.startsWith("/auctions/") ? location.pathname : `${dashboardPath}#auctions`,
      },
      { key: "payments", label: "Payments", icon: CreditCard, to: `${dashboardPath}#payments` },
      { key: "notifications", label: "Notifications", icon: Bell, to: "/notifications" },
      { key: "profile", label: "Profile", icon: UserRound, to: `${dashboardPath}#profile` },
    ],
    [dashboardPath, location.pathname],
  );

  return (
    <SignedInShellContext.Provider value={setPageMeta}>
      <div className="signed-in-shell">
        <div className="signed-in-shell__frame">
          <header className="signed-in-shell__header">
            <div className="signed-in-shell__header-copy">
              <p className="signed-in-shell__eyebrow">{roleLabel}</p>
              <p className="signed-in-shell__title">{headerMeta.title}</p>
              <p className="signed-in-shell__context">{headerMeta.contextLabel}</p>
            </div>
          </header>

          <div className="signed-in-shell__content">{children}</div>
        </div>

        <nav aria-label="Primary" className="bottom-nav">
          <div className="bottom-nav__rail">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = isNavItemActive(item.key, location.pathname, location.hash);

              return (
                <Link
                  className={`bottom-nav__link${active ? " bottom-nav__link--active" : ""}`}
                  key={item.key}
                  to={item.to}
                >
                  <Icon aria-hidden="true" className="bottom-nav__icon" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </nav>
      </div>
    </SignedInShellContext.Provider>
  );
}
