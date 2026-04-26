import AppShell, { useAppShellHeader } from "./app-shell";

export const useSignedInShellHeader = useAppShellHeader;

export default function SignedInAppShell({ children }) {
  return <AppShell>{children}</AppShell>;
}
