import fs from "fs";
import path from "path";

test("public index does not include emergent branding or badge links", () => {
  const indexHtml = fs.readFileSync(path.resolve(__dirname, "../public/index.html"), "utf8");

  expect(indexHtml).not.toMatch(/emergent/i);
  expect(indexHtml).not.toMatch(/app\.emergent\.sh/i);
});
