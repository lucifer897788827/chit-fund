import { render, screen } from "@testing-library/react";

import App from "./App";

test("renders login route shell", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /Sign In/i })).toBeInTheDocument();
});
