import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { CreditCard, FolderKanban, Gavel, Home, Settings2, UserRound } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router-dom";

import { fetchCurrentUser } from "../features/auth/api";
import { getCurrentUser, getUserRoles, updateSession } from "../lib/auth/store";

const AppShellHeaderContext = createContext(null);

function formatRoleLabel(roles) {
  if (roles.includes("admin")) {
    return "Admin";
  }
  if (roles.includes("owner") && roles.includes("subscriber")) {
    return "Owner and member";
  }
  if (roles.includes("owner")) {
    return "Owner";
  }
  if (roles.includes("subscriber")) {
    return "Member";
  }
  return "Signed in";
}

function getDefaultPageMeta(pathname) {
  if (pathname.startsWith("/groups/")) {
    return { title: "Group", contextLabel: "Members, payments, auction, and ledger" };
  }
  if (pathname === "/groups") {
    return { title: "Groups", contextLabel: "Your chit memberships and groups" };
  }
  if (pathname === "/payments") {
    return { title: "Payments", contextLabel: "Collections, dues, and balances" };
  }
  if (pathname === "/notifications") {
    return { title: "Notifications", contextLabel: "Auction and payment alerts" };
  }
  if (pathname === "/external-chits") {
    return { title: "External chits", contextLabel: "Private off-platform chit records" };
  }
  if (pathname === "/profile") {
    return { title: "Profile", contextLabel: "Account access and role status" };
  }
  if (pathname === "/admin/owner-requests") {
    return { title: "Owner requests", contextLabel: "Review subscriber upgrade requests" };
  }
  if (pathname === "/admin/users") {
    return { title: "Users", contextLabel: "Admin user directory" };
  }
  if (pathname.startsWith("/admin/users/")) {
    return { title: "User detail", contextLabel: "Admin user detail" };
  }
  if (pathname === "/admin/groups") {
    return { title: "Groups", contextLabel: "Read-only group oversight" };
  }
  if (pathname === "/admin/auctions") {
    return { title: "Auctions", contextLabel: "Read-only auction oversight" };
  }
  if (pathname === "/admin/payments") {
    return { title: "Payments", contextLabel: "Read-only payment oversight" };
  }
  if (pathname === "/admin/system") {
    return { title: "System", contextLabel: "System health and worker status" };
  }
  if (pathname.startsWith("/admin")) {
    return { title: "Dashboard", contextLabel: "System-level control" };
  }
  return { title: "Home", contextLabel: "Today in your chit fund workspace" };
}

function isNavItemActive(itemPath, pathname) {
  if (itemPath === "/home") {
    return pathname === "/home";
  }
  if (itemPath === "/groups") {
    return pathname === "/groups" || pathname.startsWith("/groups/");
  }
  return pathname === itemPath;
}

export function useAppShellHeader({ title, contextLabel }) {
  const setPageMeta = useContext(AppShellHeaderContext);

  useEffect(() => {
    if (typeof setPageMeta !== "function") {
      return undefined;
    }

    setPageMeta({ title, contextLabel });
    return () => setPageMeta(null);
  }, [contextLabel, setPageMeta, title]);
}

export default function AppShell({ children } = {}) {
  const location = useLocation();
  const [currentUser, setCurrentUser] = useState(() => getCurrentUser());
  const [pageMeta, setPageMeta] = useState(null);
  const roles = getUserRoles(currentUser);
  const roleLabel = formatRoleLabel(roles);

  useEffect(() => {
    setPageMeta(null);
  }, [location.pathname]);

  useEffect(() => {
    let active = true;

    if (!getCurrentUser()?.access_token) {
      return () => {
        active = false;
      };
    }

    fetchCurrentUser()
      .then((authState) => {
        if (!active) {
          return;
        }
        setCurrentUser(updateSession(authState));
      })
      .catch(() => {
        if (active) {
          setCurrentUser(getCurrentUser());
        }
      });

    return () => {
      active = false;
    };
  }, [location.pathname]);

  const headerMeta = {
    ...getDefaultPageMeta(location.pathname),
    ...(pageMeta ?? {}),
  };

  const navItems = useMemo(
    () =>
      roles.includes("admin") && !roles.includes("owner") && !roles.includes("subscriber")
        ? [
            { label: "Dashboard", icon: Home, to: "/admin" },
            { label: "Users", icon: UserRound, to: "/admin/users" },
            { label: "Groups", icon: FolderKanban, to: "/admin/groups" },
            { label: "Auctions", icon: Gavel, to: "/admin/auctions" },
            { label: "Payments", icon: CreditCard, to: "/admin/payments" },
            { label: "System", icon: Settings2, to: "/admin/system" },
          ]
        : [
            { label: "Home", icon: Home, to: "/home" },
            { label: "Groups", icon: FolderKanban, to: "/groups" },
            { label: "Payments", icon: CreditCard, to: "/payments" },
            { label: "Profile", icon: UserRound, to: "/profile" },
          ],
    [roles],
  );

  return (
    <AppShellHeaderContext.Provider value={setPageMeta}>
      <div className="signed-in-shell">
        <div className="signed-in-shell__frame">
          <header className="signed-in-shell__header">
            <div className="signed-in-shell__header-copy">
              <p className="signed-in-shell__eyebrow">{roleLabel}</p>
              <p className="signed-in-shell__title">{headerMeta.title}</p>
              <p className="signed-in-shell__context">{headerMeta.contextLabel}</p>
            </div>
          </header>

          <div className="signed-in-shell__content">
            {children ?? <Outlet />}
          </div>
        </div>

        <nav aria-label="Primary" className="bottom-nav">
          <div className="bottom-nav__rail">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = isNavItemActive(item.to, location.pathname);

              return (
                <Link
                  aria-current={active ? "page" : undefined}
                  className={`bottom-nav__link${active ? " bottom-nav__link--active" : ""}`}
                  key={item.to}
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
    </AppShellHeaderContext.Provider>
  );
}
