import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Bell, CreditCard, Gavel, Home, UserRound } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { fetchCurrentUser } from "../features/auth/api";
import { getCurrentUser, getDashboardPath, getUserRoles, updateSession } from "../lib/auth/store";

const SignedInShellContext = createContext(null);

function formatRoleLabel(roles) {
  if (roles.includes("admin")) {
    return "Admin";
  }
  if (roles.includes("owner") && roles.includes("subscriber")) {
    return "Owner and subscriber";
  }
  if (roles.includes("owner")) {
    return "Chit owner";
  }
  if (roles.includes("subscriber")) {
    return "Subscriber";
  }
  return "Signed in";
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
  if (pathname === "/owner" || pathname === "/owner-dashboard") {
    return {
      title: "Owner dashboard",
      contextLabel: "Groups, auctions, and collections",
    };
  }
  if (pathname === "/subscriber" || pathname === "/subscriber-dashboard") {
    return {
      title: "Subscriber dashboard",
      contextLabel: "Memberships, dues, and bidding access",
    };
  }
  if (pathname === "/admin-dashboard") {
    return {
      title: "Admin dashboard",
      contextLabel: "Owner approvals and platform oversight",
    };
  }
  return {
    title: "Workspace",
    contextLabel: "Manage your chit fund activity",
  };
}

function isNavItemActive(itemKey, pathname, hash) {
  if (itemKey === "home") {
    return (
      pathname === "/owner" ||
      pathname === "/owner-dashboard" ||
      pathname === "/subscriber" ||
      pathname === "/subscriber-dashboard" ||
      pathname === "/admin-dashboard"
    ) && !hash;
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

function isRoleHomePath(pathname) {
  return [
    "/owner",
    "/owner-dashboard",
    "/subscriber",
    "/subscriber-dashboard",
    "/admin-dashboard",
    "/admin/owner-requests",
  ].includes(pathname);
}

function normalizeRoleHomePath(pathname) {
  if (pathname === "/owner" || pathname === "/owner-dashboard") {
    return "/owner";
  }
  if (pathname === "/subscriber" || pathname === "/subscriber-dashboard") {
    return "/subscriber";
  }
  if (pathname === "/admin-dashboard" || pathname === "/admin/owner-requests") {
    return "/admin";
  }
  return pathname;
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
  const navigate = useNavigate();
  const location = useLocation();
  const [currentUser, setCurrentUser] = useState(() => getCurrentUser());
  const [pageMeta, setPageMeta] = useState(null);
  const dashboardPath = getDashboardPath(currentUser);
  const roleLabel = formatRoleLabel(getUserRoles(currentUser));

  useEffect(() => {
    setPageMeta(null);
  }, [location.pathname]);

  useEffect(() => {
    let active = true;
    const storedSession = getCurrentUser();
    setCurrentUser(storedSession);

    if (!storedSession?.access_token) {
      return () => {
        active = false;
      };
    }

    fetchCurrentUser()
      .then((authState) => {
        if (!active) {
          return;
        }

        const nextSession = updateSession(authState);
        setCurrentUser(nextSession);

        if (!isRoleHomePath(location.pathname)) {
          return;
        }

        const currentHomePath = normalizeRoleHomePath(location.pathname);
        const nextHomePath = normalizeRoleHomePath(getDashboardPath(nextSession));
        if (currentHomePath !== nextHomePath) {
          navigate(getDashboardPath(nextSession), { replace: true });
        }
      })
      .catch(() => {
        if (active) {
          setCurrentUser(getCurrentUser());
        }
      });

    return () => {
      active = false;
    };
  }, [location.pathname, navigate]);

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
