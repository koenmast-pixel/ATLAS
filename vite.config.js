import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base MOET exact overeenkomen met je repo-naam, inclusief hoofdletters.
// Repo heet ATLAS  ->  base: "/ATLAS/"
// Bij een eigen domein of een <naam>.github.io repo  ->  base: "/"
export default defineConfig({
  plugins: [react()],
  base: "/ATLAS/",
});
